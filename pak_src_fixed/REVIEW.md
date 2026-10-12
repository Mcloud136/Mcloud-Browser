# `pak_src/` 内存安全 / 过时写法 / 未定义行为 审查报告

审查对象：`D:/wxmuma/thorium/pak_src/`（Chromium `.pak` 资源包打包/解包命令行工具，纯 C，13 个 `.c/.h`）。
说明：该代码已被一轮 D1–D19 缺陷修复加固（缓冲区长度校验、4 GB 上限、别名越界、单调序等），**多数内存越界类缺陷已修复**。
**但仍有 4 类真实问题残留**：3 处严格的未定义行为（UB）、2 处“跨平台根本编不过”的可移植性错误、若干过时/危险写法，以及 1 处边界 off-by-one。

> 行号基于本次读取的源码快照。

---

## 一、未定义行为（UB）—— 必须修

### U1. `*(uint32_t *)(buffer)` 严格别名违规 + 隐式大小端假设
- 位置：`pak_defs.h:67` 宏 `pakGetVerison(buffer)`，被 `pak_header.c:9` 调用。
- 根因：buffer 实际是 `readFile` 里 `calloc` 出来的 `unsigned char` 数组，却用 `uint32_t *` 别名去解引用。C 严格别名规则（6.5p7）只允许 `char/unsigned char/signed char` 别名任意类型，**反过来不成立** → UB。在 `gcc -O2` + TBAA 下可被错误优化。
- 附带：**假设主机小端**。Chromium `.pak` 是小端格式，大端机（如某些 ARM 服务器/PPC）上会静默读错版本号。
- 修复：用 `memcpy` 取字节 + 显式小端解码（`rd_u32le`）。见修正版 `pak.c`。

### U2. 把字节 buffer 直接强转成 packed 结构体指针并解引用
- 位置：`pak_header.c:15,25`（`PakHeaderV5*`/`PakHeaderV4*`），`pak_file.c:44,45,83,95`（`PakEntry*`/`PakAlias*`），`pak_pack.c` 多处。
- 根因：`(PakHeaderV5 *)(buffer)` 这类转换后访问成员，同样违反严格别名规则。注意：`#pragma pack(1)` 只消除**对齐**问题，并**不**消除别名 UB。
- 修复：同样改用 `memcpy` 逐字段读/写（见 `rd_u16le/wr_u32le` 等），彻底消除整类 UB。

### U3. `vsnprintf` 截断判定 off-by-one（`>` 应为 `>=`）
- 位置：`pak_pack.c:34` `if (written < 0 || (uint32_t)written > capacity - offset) return 0;`
- 根因：`vsnprintf(buf, n, ...)` 当完整输出**恰好等于** `n-1` 字节时返回 `n-1`，写入 `n-1` 字节 + NUL，是成功的；但当完整输出 **== n** 字节时返回 `n`，此时只写了 `n-1` 字节（截断），应判失败。当前用 `>`，在“恰好等于边界”时**误判为成功**，导致 index 行末字节丢失 / 后续拼接错位。
- 修复：`(uint32_t)written >= capacity - offset` 即视为截断失败。修正版 `index_append()` 已用“`w < avail` 才算成功”的等价写法（见 `pak.c`）。

---

## 二、可移植性 / 跨平台编译错误（高）

### P1. `_snprintf` 是 MSVC/MinGW 专有，Linux/clang 编译失败
- 位置：`pak_pack.c:93,106,142,285`。
- 根因：`_snprintf` 非 C 标准名（C99 起标准是 `snprintf`，VS2015+ 已提供）。在 gcc/clang（Linux/macOS）下未声明 → 编译错误。`.pak` 是跨平台格式，工具本应可跨平台构建。
- 修复：统一用 `snprintf`（见 `pak.c` 全量替换）。

### P2. `PATH_MAX` 仅在 `_MSC_VER` 下定义 → MinGW 编译失败
- 位置：`pak_defs.h:5-12` 与 `main.c:201,203`（使用 `PATH_MAX`）。
- 根因：`#ifdef _MSC_VER` 才 `#include <windows.h>` 并 `#define PATH_MAX MAX_PATH`。MinGW 定义 `__MINGW32__` 而**不**定义 `_MSC_VER`，于是这段被跳过，`main.c` 里的 `PATH_MAX` 未声明 → 编译错误。
- 修复：所有 Windows 编译器统一走 `<windows.h>`/`MAX_PATH`，或定义独立的 `PAK_PATH_MAX`。见 `pak.c` 顶部宏。

### P3. `main.h` 用 `#define main ...` 重命名 `main`（仅 `_LGPL`/`-nostartfiles` 变体）
- 位置：`main.h:15` `#define main(argc, argv) _main(argc, argv)`。
- 风险：任何包含 `main.h` 的翻译单元里，所有 `main` 标识符都被静默改名；且依赖 `_pei386_runtime_relocator` 等链接期符号。属于“专家专属”的定制入口，普通构建**不应**包含它。建议保留但加醒目注释，且不要在大项目中误 include。

---

## 三、过时 / 危险写法

### O1. `strcpy` / `strncpy` 仍在使用
- 位置：`main.c:146`（`strncpy(filesPath,...)`）、`main.c:165`（`strcpy`）、`main.c:244-245`（`strcpy`）。
- 说明：`main.c:146` 的 `strncpy` 在“源恰好等于拷贝长度”时**不写 NUL 终止符**，本次靠 `calloc` 多分配的那 1 字节侥幸补零；`main.c:165/244/245` 的 `strcpy` 靠“先 `strlen` 判长度 / 同尺寸+1 分配”才安全，属于“正确但脆弱”的写法。
- 修复：改为 `snprintf` / `memcpy + 显式置 NUL`，消除对分配细节的隐式依赖（见 `pak.c` 的 `snprintf(path, sizeof(path), ...)`）。

### O2. `PakFile` 按值返回却携带堆指针 → 所有权模糊
- 位置：`pak_file.h` / `pak_file.c` / `main.c`（`pakUnpackPath`、`pakPackIndexFile`）。
- 说明：`PakFile { id, size, buffer }` 的 `buffer` 是 `malloc/calloc` 出来的，却按值传递/返回，调用方必须“知道”要对 `.buffer` 调 `free`。`pakGetFiles` 返回的数组里 `.buffer` **指向** 入参大 buffer（不可单独 free），而 `pakPackFiles` 返回的 `.buffer` 是**自己分配**的（需 free）——同一结构体两种所有权语义，极易误用。
- 修复：用清晰注释固化契约（谁分配谁释放、哪些指针是“借入”），或改为输出参数。修正版在每个函数上方写明所有权。

### O3. `NULL_File` / `freeFile` 用宏而非内联函数
- 位置：`pak_defs.h:94-95`。
- 说明：函数式宏无类型检查；`freeFile(file)` 虽只求值一次，但阅读者不易察觉它是 `free((file).buffer)`。现代 C 用 `static inline` 更安全、可被调试器单步。低优先级。

### O4. `memset(&x, 0, sizeof x)` 清零
- 位置：`pak_pack.c:171`、`main.c:202,204`。
- 说明：可行，但不如 `MyPakHeader h = {0};` 简洁且无“漏改字段大小”风险。低优先级。

---

## 四、潜在隐患 / 边界（中低）

### B1. `MyPakHeader.size` 是 `uint8_t`，却存 12（v5）/ 9（v4）
- 位置：`pak_defs.h:84`。
- 风险：当前能装下，但一旦头部扩展到 >255 字节会**静默截断**。类型语义错误，应改为 `uint32_t`。修正版已改。

### B2. `readFile` 分配 `size + 1`
- 位置：`pak_file_io.c:34`。
- 原判断（已作废）：曾写成"二进制 buffer 不需要 NUL 结尾，多分配 1 字节纯属浪费"。
- ⚠ **更正（第7周期复核，缺陷 D191）**：这 1 字节是**承重结构**。`pak_pack.c` 用 `strstr/sscanf`
  解析这块缓冲，非 NUL 终止就是堆越界读。按旧判断把 `+1` 删掉后，MSVC `/fsanitize=address`
  实测报 `heap-buffer-overflow READ of size 77`，命中点正好在 84 字节 `pak_index.ini` 之后 0 字节处
  （`__stdio_common_vsscanf`）。保留 `size+1` 并显式写 `buffer[size]='\0'`，且**不要再当冗余删除**。

### B3. `writeFile` 不检查 `ferror` / `fclose` 返回值
- 位置：`pak_file_io.c:58-65`。
- 说明：靠“`fwrite` 返回字节数 == size”大致覆盖写失败，但磁盘满 / 关闭失败可能被漏报。修正版补了 `ferror` + `fclose` 检查。

### B4. 创建输出目录时 `mkdir`/`CreateDirectory` 不递归、不判错
- 位置：`pak_pack.c:62-66`。
- 说明：多层级输出路径只建最后一级，且忽略返回值（已存在时幂等，但父目录缺失会失败）。低优先级。

---

## 五、D1–D19 加固清单（已覆盖，未回归）

以下缺陷**已被修复且修正版保留**，仅作核对：
- D1/D5 表大小 64 位求和 + 4 GB 上限；D2 `%255s` 宽度限制；D3 `resource_count==0` 防越界；D4 区段指针越界校验；D6 短读/句柄泄漏；D7 路径长度判超；D8 早返回释放整文件 buffer；D9 仅成功才报“Packed”；D10 受控路径拼接；D13 ANSI 转义修复；D15 别名循环自锁修复；D16 64 位文件长度；D17 逐资源写失败传播；D18/D19 argv 转换失败处理；D11? 等。

---

## 六、交付物

- `pak.c`：C11 单文件现代重写，**等价于**原工具（`-u/-p/-v/-h/-c` 同语义、同 `.pak` 与 `pak_index.ini` 格式），**消除全部 U1–U3 / P1 / P2 / B1**，并标注每条原始缺陷的修复点。
- `Makefile`：一键 `make` 编译（`-std=c11 -Wall -Wextra -Wpedantic`）。
- `run_test.sh`：构造样本 → 打包 → 解包 → 比对，验证格式兼容与往返正确。
- 注：本机无 C 编译器，未能在此运行；请在你本地 `make && ./run_test.sh` 验证。

---

## 七、第7周期复核记录（2026-10-12，另一位工程师逐项实测后的更正）

上面 §一–§五 的技术判断**绝大多数成立**（U1/U2/U3、P1/P2、O1、B1、B3 全部核实并保留）。
但本文件的若干**结论性表述被实测推翻**，逐条列在此处，避免后来人按原文信错：

1. **"等价于原工具"当时不成立（D190）**：`pack_files()` 写 v5 头部时没清 `_padding[3]`，
   那 3 个字节取自 `malloc` 的脏堆。对本文件随附的 `pak.exe` 连打三次，偏移 5 分别是
   `01 / 02 / 02` ⇒ 产物**不可复现**、与原工具**字节不兼容**、并把堆字节写进分发文件。
   已修（写头前 `memset`），现由 `verify_sources.check_pak_roundtrip()` 双向钉住：
   两次打包必须一致 **且** padding 必须为 0。
2. **"消除全部内存问题"过度（D191/D193/D195）**：
   - `read_file` 丢掉 `size+1` 的 NUL ⇒ `sscanf` 堆越界读（ASan 实测，见 B2 更正）；
   - `version=4` 且索引声明 `[Alias]` 时**静默丢弃别名表并返回 0**，而原工具直接拒绝（rc=8）；
   - 三处 `snprintf` 未查返回值，OOM 下会写出空的 `pak_index.ini` 却报"解包成功"。
3. **"cl /W4 零警告"有前提（D192）**：零警告来自 `/D_CRT_SECURE_NO_WARNINGS`（掩掉 4 条 C4996）
   **且** 需要 `/utf-8`。不加 `/utf-8` 时 MSVC 按 CP936 读这份无 BOM 的 UTF-8 文件会**吞掉换行**，
   警告行号整体错位——实测 4/4 条 C4996 的行号指向的都不是真正的 CRT 调用行；
   原作者的处理是 `/wd4819` 把症状闭掉。**编译本文件必须带 `/utf-8`，不要用 `/wd4819`。**
4. **"本机无 C 编译器"与仓库内容矛盾**：同一个 commit 提交了 `pak.exe`、`pak.obj`、
   `pak_test.pak`、`pak2.pak` 和 `t_out/`。产物与测试输出已从版本库移除并加进 `.gitignore`。
5. **§六 承诺的 `Makefile` / `run_test.sh` 当时并不存在**——本次复核已补写并实测：
   `run_test.sh` 对修复后的二进制 7 项全绿，对原 commit 里的 `pak.exe` 报
   `FAIL deterministic-pack` 与 `FAIL v4-alias-rejected`（这就是"判据能红"的证据）。
6. **ASan 结论的平台边界**：Windows 的 ASan **没有 LeakSanitizer**
   （实测 `ASAN_OPTIONS=detect_leaks=1` 直接以 `detect_leaks is not supported on this platform` 退出）。
   所以本目录的 ASan 结果只能证明**无越界**，不能证明**无泄漏**；泄漏判据只在 POSIX 侧
   （`verify_sources.check_pak_asan()`，ubuntu CI）成立。
7. **结构性问题（D196）**：`pak_src_fixed/` 是平行目录，修复不改变任何构建产物；而 `pak_src/`
   的源码本身也不参与构建——全仓唯一复制 pak 的是遗留的 `setup.sh` / `win_scripts/setup.py`，
   且复制的是 `pak_src/binaries/` 里的**预编译旧版**。因此"D1–D19 已加固"不等于
   "浏览器包里那个 pak 工具已加固"。

