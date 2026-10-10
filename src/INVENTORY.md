# src/ 参与度清单（自动生成，勿手工编辑）

生成命令：`python .bugreview/src_inventory.py --write`

对照的构建树：`D:\wxmuma\chromium-src-155\src`

## 结论

- 仓库 `src/` 共 **590** 个文件。
- 树内没有对应路径（真正的仓库独有资产）：**233**。
- 与树内同名文件字节一致：**12**；内容不同：**345**。
- 被构建流水线实际使用的仓库 `src/` 文件：**2** 个（见下表示）。
- 与树内不同、却没有任何脚本读取或复制它们的：**344** 个 —— 修改这些文件**不会生效、也不会报错**（缺陷 D77）。

> 所以：仓库 `src/` **不是**「当前生效的修改集」，而是一份含大量旧内核快照的
> 素材目录。要改上游文件，请在 `win_scripts/` 下写定点幂等脚本（`apply_*` /
> `inject_*`）并由 `deploy_mcloud.py` 编排；不要把仓库副本加进
> `copy_essentials.py` 的整份复制清单——那里的白名单会直接拒绝有上游对应物的
> 条目（缺陷 D41）。

## 实际参与构建的仓库 src/ 文件

| 文件 | 使用方式 | 与对照树比对 |
|------|----------|--------------|
| `src/build/config/compiler_opt.gni` | copy | 与树内一致 |
| `src/chrome/app/chrome_main_delegate.cc` | inject-target（副本不生效） | 与树内不同 |

## 与树内不同、且无人使用的副本（前 60 条，按路径序）

这些是历史遗留快照（多为旧内核基线，含上一代注入痕迹）。列在这里只为回答
「这个文件到底有没有用」——答案是：没有。

```
src/BUILD.gn  repo=c8a0408e5281 tree=e38b612778a4
src/ash/resources/vector_icons/files_app.icon  repo=bf1a250c5b33 tree=338f22b98ce0
src/ash/resources/vector_icons/system_menu_info.icon  repo=5d6958f16c43 tree=59d41e4f359c
src/ash/resources/vector_icons/unified_menu_info.icon  repo=ac6a8d12640d tree=803b6dee8d2c
src/ash/webui/help_app_ui/resources/app.html  repo=2abb29bb280d tree=686c8ca427b4
src/ash/webui/sample_system_web_app_ui/BUILD.gn  repo=0bb318bc7f85 tree=33cdbd118afd
src/ash/webui/sample_system_web_app_ui/mojom/BUILD.gn  repo=dca71f10074e tree=cf02c843e1a7
src/ash/webui/sample_system_web_app_ui/resources/trusted/BUILD.gn  repo=d2b72c57da97 tree=b2167b87f293
src/ash/webui/sample_system_web_app_ui/resources/untrusted/BUILD.gn  repo=8b91de565e5b tree=ad0026cfc5fb
src/build/config/BUILDCONFIG.gn  repo=8a5547d46a8a tree=a054690eef89
src/build/config/android/BUILD.gn  repo=c9bb7209fa2e tree=dc7ba0129492
src/build/config/arm.gni  repo=ed81b0c31275 tree=30facd95ba6f
src/build/config/compiler/BUILD.gn  repo=fef928c76ab4 tree=2799182d7a94
src/build/config/mac/BUILD.gn  repo=78e07c64bf73 tree=ce35f20e1ebf
src/build/config/win/BUILD.gn  repo=fa7803388636 tree=e1bc92846317
src/build/install-build-deps.py  repo=5d1f65ea6636 tree=a71e5ed8e3cb
src/build/toolchain/apple/linker_driver.py  repo=195cdb935a1d tree=0b0f5458b7f6
src/build/vs_toolchain.py  repo=c4c4ae420aff tree=032620538c81
src/build/win/reorder-imports.py  repo=c79d006fb94e tree=6850df690364
src/chrome/BUILD.gn  repo=7195a3e7b4e6 tree=b94f91e92941
src/chrome/android/BUILD.gn  repo=98c5d82fa3aa tree=5b4fe0217f8f
src/chrome/android/chrome_java_resources.gni  repo=47e585cc84b9 tree=c79e8ee6adf0
src/chrome/android/chrome_public_apk_tmpl.gni  repo=0cc53ef27a44 tree=326a15927e5e
src/chrome/android/java/res/drawable-hdpi/incognito_splash.png  repo=7bab428647b3 tree=a74168bb0c9f
src/chrome/android/java/res/drawable-mdpi/incognito_splash.png  repo=e8f62cc98bc2 tree=0c721126380d
src/chrome/android/java/res/drawable-xhdpi/incognito_splash.png  repo=fe83f4e29048 tree=b135c4203390
src/chrome/android/java/res/drawable-xxhdpi/incognito_splash.png  repo=60a391d8497c tree=27bdbb581514
src/chrome/android/java/res/drawable-xxxhdpi/incognito_splash.png  repo=498b95af63f2 tree=0c2abb6d8a33
src/chrome/android/java/res_base/drawable/ic_launcher_round.xml  repo=4ae65d65952d tree=c059dc4d529f
src/chrome/android/java/res_chromium_base/drawable/themed_app_icon.xml  repo=6e3b69592152 tree=34fbf3ef9831
src/chrome/android/java/res_chromium_base/mipmap-hdpi/app_icon.png  repo=a37bb73d95cf tree=bde30be3e4ae
src/chrome/android/java/res_chromium_base/mipmap-hdpi/layered_app_icon.png  repo=917755fdd33f tree=6268fd657951
src/chrome/android/java/res_chromium_base/mipmap-mdpi/app_icon.png  repo=e89c0debf341 tree=1bc10140ad5a
src/chrome/android/java/res_chromium_base/mipmap-mdpi/layered_app_icon.png  repo=60a008d15cef tree=046f9881eb69
src/chrome/android/java/res_chromium_base/mipmap-xhdpi/app_icon.png  repo=1fe933c97973 tree=42fd3e07cea0
src/chrome/android/java/res_chromium_base/mipmap-xhdpi/layered_app_icon.png  repo=226f06eac8c7 tree=bdd48fa8adf0
src/chrome/android/java/res_chromium_base/mipmap-xxhdpi/app_icon.png  repo=4d53e5cddc96 tree=098e8f3cca5c
src/chrome/android/java/res_chromium_base/mipmap-xxhdpi/layered_app_icon.png  repo=61978e17431d tree=1271a7785538
src/chrome/android/java/res_chromium_base/mipmap-xxxhdpi/app_icon.png  repo=1a4bda2d2b84 tree=dffc9b779d5e
src/chrome/android/java/res_chromium_base/mipmap-xxxhdpi/layered_app_icon.png  repo=dab54c7a61cb tree=4866c1095627
src/chrome/android/java/res_chromium_base/values/channel_constants.xml  repo=5177da95eaf9 tree=bfbe36ebd7f5
src/chrome/app/app_management_strings.grdp  repo=d68c4c30a1f1 tree=a82ab8a811ab
src/chrome/app/chrome_exe.ver  repo=cadc28017a48 tree=ed401e36dc6e
src/chrome/app/chrome_exe.vsprops  repo=dacba20cc155 tree=d68899e62c99
src/chrome/app/chromium_strings.grd  repo=6a43e548f0c2 tree=848216b77ae1
src/chrome/app/generated_resources.grd  repo=5d2082a727be tree=4413c6043f4b
src/chrome/app/resources/manpage.1.in  repo=86cf8f9eb7d2 tree=6838c7c3b91e
src/chrome/app/settings_chromium_strings.grdp  repo=0f3baea0d748 tree=9fb3a5d1020f
src/chrome/app/settings_strings.grdp  repo=dc900ee84a01 tree=ff45194a6b8b
src/chrome/app/shared_settings_strings.grdp  repo=8ff4f4d6bd53 tree=4f87b89a52bd
src/chrome/app/theme/chromium/BRANDING  repo=3b803bdaf01f tree=3ede4417db36
src/chrome/app/theme/chromium/chromeos/chrome_app_icon_192.png  repo=8891b35ee030 tree=c55d484c5273
src/chrome/app/theme/chromium/chromeos/chrome_app_icon_32.png  repo=1553a8bcf5d0 tree=706adc1ce808
src/chrome/app/theme/chromium/linux/product_logo_128.png  repo=f559a3f4dbaf tree=ae9d84286a3f
src/chrome/app/theme/chromium/linux/product_logo_24.png  repo=2fa39c8431ec tree=f305188d6e14
src/chrome/app/theme/chromium/linux/product_logo_256.png  repo=043f6c28c145 tree=190dc5dbd72d
src/chrome/app/theme/chromium/linux/product_logo_32.xpm  repo=dadaf7b18552 tree=8862dff5f347
src/chrome/app/theme/chromium/linux/product_logo_48.png  repo=36eb03d6929b tree=25a8c0aeab4e
src/chrome/app/theme/chromium/linux/product_logo_64.png  repo=cc7f3757d0e9 tree=aa925e4c764b
src/chrome/app/theme/chromium/mac/app.icns  repo=7dde38919a1b tree=a1c2b1719123
... 另有 284 条
```
