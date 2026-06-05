#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors and Alex313031
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))
import installer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a", "--arch", required=True, help="deb package architecture")
    parser.add_argument(
        "-b", "--build-time", required=True, help="build timestamp")
    parser.add_argument(
        "-c", "--channel", required=True, help="package channel")
    parser.add_argument("-d", "--branding", required=True, help="branding")
    parser.add_argument(
        "-f", "--official", action="store_true", help="official build")
    parser.add_argument(
        "-n", "--name-suffix", default="", help="package filename suffix")
    parser.add_argument(
        "-o", "--output-dir", required=True, help="output directory")
    parser.add_argument("-s", "--sysroot", required=True, help="sysroot")
    parser.add_argument("-t", "--target-os", required=True, help="target os")
    return parser.parse_args()


def gen_control(context, staging_dir, deb_control, deb_changelog, deb_files,
                pkg_name):
    cmd = [
        "dpkg-gencontrol",
        f"-v{context['VERSIONFULL']}",
        f"-c{deb_control}",
        f"-l{deb_changelog}",
        f"-f{deb_files}",
        f"-p{pkg_name}",
        f"-P{staging_dir}",
        "-O",
    ]

    output_control = staging_dir / "DEBIAN/control"
    with output_control.open("w") as f:
        if os.environ.get("VERBOSE"):
            subprocess.check_call(cmd, stdout=f)
        else:
            subprocess.check_call(cmd, stdout=f, stderr=subprocess.DEVNULL)

    deb_control.unlink()


def verify_package(context, deb_file):
    depends = context["DEPENDS"]
    expected_depends = [d.strip() for d in depends.split(", ") if d.strip()]

    output = subprocess.check_output(["dpkg", "-I", str(deb_file)], text=True)
    actual_depends = []
    for line in output.splitlines():
        if line.startswith(" Depends: "):
            deps = line[len(" Depends: "):].split(", ")
            actual_depends = [d.strip() for d in deps if d.strip()]
            break

    installer.verify_package_deps(expected_depends, actual_depends)


def main():
    os.umask(0o022)
    args = parse_args()
    is_official_build = True

    log_level = logging.INFO if os.environ.get("VERBOSE") else logging.ERROR
    logging.basicConfig(level=log_level, format="%(message)s")

    script_dir = pathlib.Path(__file__).parent.absolute()
    output_dir = pathlib.Path(args.output_dir)

    staging_dir = output_dir / "deb-staging"
    tmp_file_dir = output_dir / "deb-tmp"

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    if tmp_file_dir.exists():
        shutil.rmtree(tmp_file_dir)

    staging_dir.mkdir(parents=True, exist_ok=True)
    tmp_file_dir.mkdir(parents=True, exist_ok=True)

    deb_changelog = tmp_file_dir / "changelog"
    deb_files = tmp_file_dir / "files"
    deb_control = tmp_file_dir / "control"

    inst = installer.Installer(
        output_dir,
        staging_dir,
        args.channel,
        args.branding,
        args.arch,
        args.target_os,
        is_official_build,
    )

    inst.set_context({
        "ARCHITECTURE": args.arch,
        "BRANDING": args.branding,
        "BUILD_TIMESTAMP": args.build_time,
        "IS_OFFICIAL_BUILD": 1,
        "OUTPUTDIR": output_dir,
        "SCRIPTDIR": script_dir,
        "STAGEDIR": staging_dir,
        "TMPFILEDIR": tmp_file_dir,
    })

    inst.initialize()
    channel = inst.channel

    # Export variables for dpkg tools
    os.environ["ARCHITECTURE"] = args.arch
    os.environ["DEBEMAIL"] = inst.context["MAINTMAIL"]
    os.environ["DEBFULLNAME"] = inst.context["MAINTNAME"]

    # Calculate deps
    deb_common_deps_file = output_dir / "deb_common.deps"
    with deb_common_deps_file.open("r") as f:
        common_deps = f.read().strip().replace("\n", ", ")
    inst.context["COMMON_DEPS"] = common_deps
    inst.context["COMMON_PREDEPS"] = "dpkg (>= 1.14.0)"

    inst.context["SHLIB_PERMS"] = 0o644

    # Thorium does not install a Google Chrome apt repository.
    inst.context["REPOCONFIG"] = ""
    inst.context["REPOCONFIGREGEX"] = ""

    # Prep staging debian
    inst.prep_staging_common()
    (staging_dir / "DEBIAN").mkdir(parents=True, exist_ok=True)
    (staging_dir / "DEBIAN").chmod(0o755)
    (staging_dir / "etc/cron.daily").mkdir(parents=True, exist_ok=True)
    (staging_dir / "etc/cron.daily").chmod(0o755)
    (staging_dir /
     f"usr/share/doc/{inst.context['USR_BIN_SYMLINK_NAME']}").mkdir(
         parents=True, exist_ok=True)
    (staging_dir /
     f"usr/share/doc/{inst.context['USR_BIN_SYMLINK_NAME']}").chmod(0o755)

    inst.stage_install_common()

    logging.info(f"Staging Debian install files in '{staging_dir}'...")
    install_dir = staging_dir / inst.context["INSTALLDIR"].lstrip("/")
    cron_dir = install_dir / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)
    cron_dir.chmod(0o755)

    cron_file = cron_dir / inst.context["PACKAGE"]
    installer.process_template(output_dir / "installer/common/repo.cron",
                               cron_file, inst.context)
    cron_file.chmod(0o755)

    cron_daily_link = staging_dir / "etc/cron.daily" / inst.context["PACKAGE"]
    if cron_daily_link.is_symlink() or cron_daily_link.exists():
        cron_daily_link.unlink()
    os.symlink(
        os.path.join(inst.context["INSTALLDIR"], "cron",
                     inst.context["PACKAGE"]),
        cron_daily_link,
    )

    for script in ["postinst", "prerm", "postrm"]:
        dest = staging_dir / "DEBIAN" / script
        installer.process_template(output_dir / f"installer/debian/{script}",
                                   dest, inst.context)
        dest.chmod(0o755)

    # Restore PACKAGE for control template
    inst.context["PACKAGE"] = inst.context["PACKAGE_ORIG"]

    logging.info(f"Packaging {args.arch}...")
    inst.context["PREDEPENDS"] = inst.context["COMMON_PREDEPS"]
    inst.context["DEPENDS"] = inst.context["COMMON_DEPS"]
    inst.context["PROVIDES"] = "www-browser"

    installer.gen_changelog(inst.context, staging_dir, deb_changelog)
    installer.process_template(script_dir / "control.template", deb_control,
                               inst.context)

    os.environ["DEB_HOST_ARCH"] = args.arch
    pkg_name = inst.context["PACKAGE_ORIG"]

    if deb_control.exists():
        gen_control(
            inst.context,
            staging_dir,
            deb_control,
            deb_changelog,
            deb_files,
            pkg_name,
        )

    os.environ["SOURCE_DATE_EPOCH"] = args.build_time
    staging_dir.chmod(0o750)
    installer.run_command([
        "fakeroot",
        "dpkg-deb",
        "-Znone",
        "-b",
        str(staging_dir),
        str(tmp_file_dir),
    ])

    package_file = f"{pkg_name}_{inst.context['VERSIONFULL']}_{args.arch}.deb"
    package_path = tmp_file_dir / package_file

    if is_official_build:
        pkg_basename = package_path.name
        installer.run_command(["ar", "-x", pkg_basename], cwd=tmp_file_dir)
        installer.run_command([
            "xz",
            "-z9",
            "-T0",
            "--lzma2=dict=256MiB",
            str(tmp_file_dir / "data.tar"),
        ])
        installer.run_command(["xz", "-z0", str(tmp_file_dir / "control.tar")])
        installer.run_command(
            ["ar", "-d", pkg_basename, "control.tar", "data.tar"],
            cwd=tmp_file_dir,
        )
        installer.run_command(
            ["ar", "-r", pkg_basename, "control.tar.xz", "data.tar.xz"],
            cwd=tmp_file_dir,
        )

    final_package_path = output_dir / (
        f"{inst.context['PACKAGE_ORIG']}_{inst.context['VERSION']}"
        f"{args.name_suffix}.deb")
    shutil.move(package_path, final_package_path)

    verify_package(inst.context, final_package_path)

    # cleanup
    shutil.rmtree(staging_dir)
    shutil.rmtree(tmp_file_dir)


if __name__ == "__main__":
    main()
