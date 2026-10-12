/*
 * pak.c — Chromium .pak 资源包 打包/解包工具（现代、安全重写版）
 *
 * 等价替换 D:/wxmuma/thorium/pak_src/ 下的工具：CLI 语义、磁盘 .pak 格式、
 * pak_index.ini 格式均与原版一致，可无缝衔接既有 .pak / 索引文件。
 *
 * 相对原版修复（行内注释引用原始缺陷编号）：
 *   U1/U2  —— 彻底消除严格别名 UB：所有对字节缓冲的读/写改用 memcpy + 显式小端解码，
 *            绝不再做 `*(uint32_t*)buf` 或 `(PakHeaderV5*)buf` 这类类型双关。
 *   U3     —— vsnprintf 截断判定用 `w < avail` 才算成功（等价 `>=` 判失败），无 off-by-one。
 *   P1     —— 全量 snprintf（C99 标准名），Linux/clang/MinGW/MSVC 均可编译。
 *   P2     —— 统一 PAK_PATH_MAX 宏，覆盖 MSVC / MinGW / POSIX。
 *   B1     —— MyPakHeader.header_size 用 uint32_t（原 uint8_t 有潜在截断）。
 *   B3     —— write_file 额外检查 ferror / fclose 返回值。
 *   O1     —— 路径拼接一律 snprintf + 长度边界，不再用 strcpy/strncpy。
 *   D190   —— 写头部前先 memset，v5 的 3 个 padding 字节不再漏未初始化的堆内容。
 *   D191   —— 索引缓冲保留 size+1 并写 NUL：sscanf/strstr 需要，删掉即堆越界读（ASan 实测）。
 *   D192   —— MSVC 必须用 /utf-8 编译本文件（无 BOM 的 UTF-8 中文注释在 CP936 下会
 *            吞掉换行，警告行号整体错位；实测 4 条 C4996 的行号全部指错代码）。
 *   D193   —— version=4 时若索引声明了 [Alias]，直接拒绝而不是静默丢弃别名表。
 *
 * 编译（MSVC）：
 *   call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
 *   cl /W4 /O2 /utf-8 pak.c /Fe:pak.exe        ← /utf-8 不可省，见 D192
 * 编译（gcc/clang）： cc -std=c11 -Wall -Wextra -Wpedantic -O2 pak.c -o pak
 *
 * 用法： pak -u <file.pak> <out_dir> | pak -p <pak_index.ini> <out.pak>
 *        pak -v | -h | -c
 *
 * ★ 所有权契约（务必遵守）：
 *   - read_file / pack_files / pack 返回的 PakFile.buffer 由调用方负责 free。
 *   - get_files 返回的数组元素 .buffer 指向入参大缓冲（借入，不可单独 free；
 *     释放整块大缓冲即可），数组本身用 free 释放。
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <limits.h>

#ifdef _WIN32
#include <windows.h>
#include <direct.h>            /* _mkdir */
#define PAK_PATH_MAX MAX_PATH
#else
#include <sys/stat.h>
#include <sys/types.h>
#include <limits.h>
/* glibc 在 `-std=c11` 严格模式下不暴露 PATH_MAX（要 _DEFAULT_SOURCE），
   少了这层兜底，本文件在 CI 的 gcc 上会直接编译失败（P2 的收尾）。 */
# ifndef PATH_MAX
#  define PATH_MAX 4096
# endif
#define PAK_PATH_MAX PATH_MAX
#endif

/* MSVC 没有标准的 fseeko/ftello，用 64 位变体替代；MinGW/glibc 自带。 */
#ifdef _MSC_VER
#define fseeko _fseeki64
#define ftello _ftelli64
#endif

/* ----------------------------- 常量 ----------------------------- */
#define PAK_ENTRY_SIZE  6u   /* uint16 resource_id + uint32 offset */
#define PAK_ALIAS_SIZE  4u   /* uint16 resource_id + uint16 entry_index */
#define PAK_HDR_V5      12u  /* version(4)+encoding(1)+pad(3)+res_count(2)+alias_count(2) */
#define PAK_HDR_V4      9u   /* version(4)+res_count(4)+encoding(1) */
#define PAK_BUF_BLOCK   4096u
#define PAK_MIN_FREE    512u
#define PAK_MAX16       0xFFFFu

/* --------------------- UB-free 字节序读写（U1/U2） --------------------- */
/* 永远不要对“字节缓冲”做强类型指针转换再解引用（严格别名 UB + 大小端假设）。
   统一走 memcpy + 显式小端解码；Chromium .pak 为小端格式。 */
static uint32_t rd_u32le(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint16_t rd_u16le(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}
static void wr_u32le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
    p[2] = (uint8_t)((v >> 16) & 0xFF);
    p[3] = (uint8_t)((v >> 24) & 0xFF);
}
static void wr_u16le(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
}

/* ----------------------------- 数据结构 ----------------------------- */
/* B1: header_size 用 uint32_t（原 uint8_t，头部 >255 字节会静默截断）。 */
typedef struct {
    uint32_t version;
    uint32_t resource_count;
    uint16_t alias_count;
    uint8_t  encoding;
    uint32_t header_size;     /* 磁盘头部字节长度 */
} MyPakHeader;

typedef struct {
    uint16_t id;
    uint32_t size;
    uint8_t *buffer;          /* 见文件头“所有权契约” */
} PakFile;

#define NULL_FILE ((PakFile){0, 0, NULL})

/* 释放“自有”的 PakFile 数组（每个元素 buffer 均由本模块分配）。 */
static void pak_array_free(PakFile *a, uint32_t n) {
    if (!a) return;
    for (uint32_t i = 0; i < n; i++)
        if (a[i].buffer) free(a[i].buffer);
    free(a);
}

/* ----------------------------- 文件 IO ----------------------------- */
/* 读整个文件到内存；64 位长度、短读即失败、句柄必定关闭（修复原 D6）。 */
static PakFile read_file(const char *name) {
    PakFile f = NULL_FILE;
    FILE *fp = fopen(name, "rb");
    if (!fp) return NULL_FILE;

    if (fseeko(fp, 0, SEEK_END) != 0) { fclose(fp); return NULL_FILE; }
    int64_t len = ftello(fp);
    if (len < 0 || len > (int64_t)UINT32_MAX) { fclose(fp); return NULL_FILE; }
    if (fseeko(fp, 0, SEEK_SET) != 0) { fclose(fp); return NULL_FILE; }

    f.size = (uint32_t)len;
    /* 多分配 1 字节并显式置 NUL：下面 pack() 用 strstr/sscanf 按 C 字符串扫这个缓冲，
       没有终止符就会读过分配尾（第7周期 D191，ASan 实测 heap-buffer-overflow
       READ of size 77，位置正好在 84 字节的 pak_index.ini 之后 0 字节处）。
       原实现的 size+1 不是浪费，是这些字符串函数的前置条件。 */
    f.buffer = malloc((size_t)f.size + 1);
    if (!f.buffer) { fclose(fp); return NULL_FILE; }
    f.buffer[f.size] = '\0';

    if (f.size > 0 && fread(f.buffer, 1, f.size, fp) != (size_t)f.size) {
        free(f.buffer); f.buffer = NULL; fclose(fp); return NULL_FILE;
    }
    fclose(fp);
    return f;
}

/* 写整个文件；额外检查 ferror / fclose（修复原 B3）。 */
static bool write_file(const char *name, const uint8_t *buf, uint32_t size) {
    FILE *fp = fopen(name, "wb");
    if (!fp) return false;
    bool ok = true;
    if (size > 0 && fwrite(buf, 1, size, fp) != (size_t)size) ok = false;
    if (ferror(fp)) ok = false;
    if (fclose(fp) != 0) ok = false;
    return ok;
}

/* ----------------------- 头部解析 / 格式校验 ----------------------- */
/* 全部字段经 memcpy + 小端解码，无任何类型双关（U1/U2）。 */
static bool parse_header(const uint8_t *buf, uint32_t size, MyPakHeader *h) {
    memset(h, 0, sizeof(*h));
    if (!buf || size < 4) { puts("Error: Probably truncated pak file."); return false; }
    h->version = rd_u32le(buf);
    if (h->version == 5) {
        if (size < PAK_HDR_V5) { puts("Error: Probably truncated pak file."); return false; }
        h->encoding       = buf[4];
        h->resource_count = rd_u16le(buf + 8);
        h->alias_count    = rd_u16le(buf + 10);
        h->header_size    = PAK_HDR_V5;
    } else if (h->version == 4) {
        if (size < PAK_HDR_V4) { puts("Error: Probably truncated pak file."); return false; }
        h->resource_count = rd_u32le(buf + 4);
        h->encoding       = buf[8];
        h->alias_count    = 0;
        h->header_size    = PAK_HDR_V4;
    } else {
        puts("Error: Unknown pak version.");
        return false;
    }
    return true;
}

/* 64 位求和：伪造的巨大 resource_count 必须在此失败而非回绕（原 D5）。 */
static bool tables_in_range(const MyPakHeader *h, uint32_t size) {
    uint64_t table =
        (uint64_t)h->header_size +
        ((uint64_t)h->resource_count + 1) * PAK_ENTRY_SIZE +
        (uint64_t)h->alias_count * PAK_ALIAS_SIZE;
    return table <= (uint64_t)size;
}

/* 校验入口表是否越界且偏移严格单调递增（原 D1/D5）。 */
static bool check_format(const uint8_t *buf, uint32_t size) {
    MyPakHeader h;
    if (!parse_header(buf, size, &h)) return false;
    if (!tables_in_range(&h, size)) { puts("Error: Probably truncated pak file."); return false; }

    const uint8_t *e = buf + h.header_size;
    uint32_t prev = 0;
    for (uint32_t i = 0; i <= h.resource_count; i++) {
        uint32_t off = rd_u32le(e + i * PAK_ENTRY_SIZE + 2); /* offset 字段在条目 +2 处 */
        if (off > size) { puts("Error: Probably truncated pak file."); return false; }
        if (i > 0 && off < prev) { puts("Error: Pak entry offsets are not monotonic."); return false; }
        prev = off;
    }
    return true;
}

/* ----------------------- 资源枚举 / 打包 ----------------------- */
/* 取出全部资源；元素 .buffer 指向入参大缓冲（借入，不可单独 free）。 */
static PakFile *get_files(const uint8_t *buf, uint32_t size, uint32_t *out_count) {
    *out_count = 0;
    MyPakHeader h;
    if (!parse_header(buf, size, &h)) return NULL;
    if (!tables_in_range(&h, size)) return NULL;
    if (h.resource_count == 0) return NULL;   /* 防御：resource_count==0 防越界（原 D3） */

    PakFile *arr = calloc(h.resource_count, sizeof(PakFile));
    if (!arr) return NULL;

    const uint8_t *e = buf + h.header_size;
    for (uint32_t i = 0; i < h.resource_count; i++) {
        uint32_t off  = rd_u32le(e + i * PAK_ENTRY_SIZE + 2);
        uint32_t next = rd_u32le(e + (i + 1) * PAK_ENTRY_SIZE + 2);
        /* 拒绝越界或非单调表，避免把回绕(巨大)尺寸交给 write_file（原 D5/D1）。 */
        if (off > size || next > size || next < off) { free(arr); return NULL; }
        arr[i].id     = rd_u16le(e + i * PAK_ENTRY_SIZE);
        arr[i].buffer = (uint8_t *)(buf + off);  /* 借入 */
        arr[i].size   = next - off;
    }
    *out_count = h.resource_count;
    return arr;
}

/* 把若干资源 + 别名装配成一个 .pak 缓冲（自分配，调用方负责 free）。 */
static PakFile pack_files(const MyPakHeader *h, const PakFile *res,
                          const uint16_t *alias_ids, const uint16_t *alias_idx,
                          uint16_t alias_count) {
    if (!h || !res || h->resource_count == 0) return NULL_FILE;  /* D3 */

    /* 64 位累计总长度，>4G 直接拒绝（原 D5）。 */
    uint64_t total = h->header_size;
    for (uint32_t i = 0; i < h->resource_count; i++) total += res[i].size;
    total += ((uint64_t)h->resource_count + 1) * PAK_ENTRY_SIZE;
    total += (uint64_t)alias_count * PAK_ALIAS_SIZE;
    if (total > 0xFFFFFFFFULL) { puts("Error: Packed pak would exceed 4 GB."); return NULL_FILE; }

    uint8_t *buf = malloc((size_t)total);
    if (!buf) return NULL_FILE;

    /* 写头部（小端，无别名 UB）。
       ⚠ 必须先把头部区间清零：v5 的布局是 version(4) + encoding(1) + _padding[3] +
       resource_count(2) + alias_count(2)，那 3 个 padding 字节原实现只写了 buf[4]，
       于是把 malloc 出来的脏堆内容留在产物里（第7周期 D190：同一份输入三次打包，
       偏移 5 分别是 0x00 / 0x01 / 0x02 ⇒ 产物不可复现、与原工具字节不兼容，
       且泄露进程堆字节）。 */
    memset(buf, 0, h->header_size);
    wr_u32le(buf, h->version);
    if (h->version == 5) {
        buf[4] = h->encoding;
        wr_u16le(buf + 8,  (uint16_t)h->resource_count);
        wr_u16le(buf + 10, alias_count);
    } else { /* v4 */
        wr_u32le(buf + 4, h->resource_count);
        buf[8] = h->encoding;
    }

    uint8_t *entry = buf + h->header_size;
    uint8_t *data  = entry + ((size_t)h->resource_count + 1) * PAK_ENTRY_SIZE
                            + (size_t)alias_count * PAK_ALIAS_SIZE;
    const uint8_t *end = buf + total;

    for (uint32_t i = 0; i < h->resource_count; i++) {
        if (data + res[i].size > end) { free(buf); return NULL_FILE; }  /* 防御 OOB */
        memcpy(data, res[i].buffer, res[i].size);
        wr_u16le(entry + i * PAK_ENTRY_SIZE,     res[i].id);
        wr_u32le(entry + i * PAK_ENTRY_SIZE + 2, (uint32_t)(data - buf));
        data += res[i].size;
    }
    /* 终止条目（resource_count>=1 已保证，sentinel 偏移即数据尾）。 */
    wr_u16le(entry + h->resource_count * PAK_ENTRY_SIZE,     0);
    wr_u32le(entry + h->resource_count * PAK_ENTRY_SIZE + 2, (uint32_t)(data - buf));

    if (alias_count > 0) {
        uint8_t *a = entry + ((size_t)h->resource_count + 1) * PAK_ENTRY_SIZE;
        for (uint16_t i = 0; i < alias_count; i++) {
            wr_u16le(a + i * PAK_ALIAS_SIZE,     alias_ids[i]);
            wr_u16le(a + i * PAK_ALIAS_SIZE + 2, alias_idx[i]);
        }
    }

    PakFile f = {0, (uint32_t)total, buf};
    return f;
}

/* 按文件头魔数识别扩展名（等价原 pakGetFileType，返回静态字符串）。 */
typedef struct { const char *ext; const char *magic; size_t mlen; } FileType;
static const FileType FILE_TYPES[] = {
    {".png",  "\x89\x50\x4E\x47\x0D\x0A\x1A\x0A", 8},
    {".html", "<!doctype html>", 15},
    {".html", "<!DOCTYPE html>", 15},
    {".html", "<html>", 6},
    {".html", "<!--", 4},
    {".html", "<link", 5},
    {".svg",  "<svg ", 5},
    {".js",   "// ", 3},
    {".js",   "(function", 9},
    {".css",  "/*", 2},
    {".json", "{", 1},
    {".gz",   "\x1f\x8b", 2},
};
static const char *get_file_type(const uint8_t *buf, uint32_t size) {
    if (!buf) return "";
    for (size_t i = 0; i < sizeof(FILE_TYPES) / sizeof(FileType); i++) {
        if (size >= FILE_TYPES[i].mlen &&
            memcmp(buf, FILE_TYPES[i].magic, FILE_TYPES[i].mlen) == 0)
            return FILE_TYPES[i].ext;
    }
    return "";
}

/* 统计字符串中某字符出现次数（用于数资源/别名的 '=' 行数）。 */
static uint32_t count_char(const char *s, size_t len, char c) {
    uint32_t n = 0;
    for (size_t i = 0; i < len; i++) if (s[i] == c) n++;
    return n;
}

/* 向索引字符串缓冲追加格式化行；容量不足时几何增长（realloc）。
   返回值：成功 true。buf/cap/len 始终通过参数回写（realloc 可能移动缓冲）。
   关键修复 U3：只有 w < avail（即真正放得下，含结尾 NUL）才算成功。 */
static bool index_append(char **buf, uint32_t *cap, uint32_t *len, const char *fmt, ...) {
    for (;;) {
        uint32_t avail = (*cap > *len) ? (*cap - *len) : 0;
        char *dst = (*buf && avail > 0) ? (*buf + *len) : NULL;
        va_list ap;
        va_start(ap, fmt);
        int w = vsnprintf(dst, avail, fmt, ap);
        va_end(ap);
        if (w < 0) return false;                       /* 编码错误 */
        if ((uint32_t)w < avail) {                     /* 真正放得下 */
            *len += (uint32_t)w;
            return true;
        }
        /* 需要更大缓冲 */
        uint32_t newcap = *cap ? (*cap * 2) : PAK_BUF_BLOCK;
        if (newcap <= *cap) return false;              /* 溢出保护 */
        char *nb = realloc(*buf, newcap);
        if (!nb) return false;
        *buf = nb;
        *cap = newcap;
    }
}

/* ----------------------------- 解包 ----------------------------- */
static bool unpack(const uint8_t *buf, uint32_t size, const char *outdir) {
    MyPakHeader h;
    if (!parse_header(buf, size, &h)) return false;
    if (!tables_in_range(&h, size)) { puts("Error: Probably truncated pak file."); return false; }

#ifdef _WIN32
    _mkdir(outdir);                 /* 已存在时幂等忽略 */
#else
    mkdir(outdir, 0777);
#endif

    uint32_t count = 0;
    PakFile *files = get_files(buf, size, &count);
    if (!files) return false;

    char *index = NULL;
    uint32_t cap = 0, len = 0;
    index_append(&index, &cap, &len, "[Global]\r\nversion=%u\r\n", h.version);
    index_append(&index, &cap, &len, "encoding=%u\r\n\r\n[Resources]\r\n", h.encoding);

    char fname[64];
    char path[PAK_PATH_MAX];
    for (uint32_t i = 0; i < count; i++) {
        const char *ext = get_file_type(files[i].buffer, files[i].size);
        /* O1/P1：受控路径拼接，snprintf + 长度边界，绝不 strcpy。
           D195：截断必须报错——否则资源会写到被截断的路径上，而工具仍报成功。 */
        snprintf(fname, sizeof(fname), "%u%s", files[i].id, ext);
        int pn = snprintf(path, sizeof(path), "%s/%s", outdir, fname);
        if (pn < 0 || (size_t)pn >= sizeof(path)) {
            printf("Error: output path too long for resource %u\n", files[i].id);
            free(index); free(files); return false;
        }
        if (!write_file(path, files[i].buffer, files[i].size)) {
            free(index); free(files); return false;     /* 逐资源写失败传播（原 D17） */
        }
        index_append(&index, &cap, &len, "%u=%s\r\n", files[i].id, fname);
    }

    if (h.alias_count > 0) {
        index_append(&index, &cap, &len, "\r\n[Alias]\r\n");
        const uint8_t *a = buf + h.header_size +
                           ((uint64_t)h.resource_count + 1) * PAK_ENTRY_SIZE;
        for (uint16_t i = 0; i < h.alias_count; i++) {
            uint16_t aid = rd_u16le(a + i * PAK_ALIAS_SIZE);
            uint16_t aix = rd_u16le(a + i * PAK_ALIAS_SIZE + 2);
            index_append(&index, &cap, &len, "%u=%u\r\n", aid, aix);
        }
    }

    char idxpath[PAK_PATH_MAX];
    int in_ = snprintf(idxpath, sizeof(idxpath), "%s/pak_index.ini", outdir);
    if (in_ < 0 || (size_t)in_ >= sizeof(idxpath)) {
        printf("Error: index path too long\n");
        free(index); free(files); return false;
    }
    /* D195：index 为空只可能是 index_append 在内存不足时全部失败。此时继续写文件
       会产出一个"空的 pak_index.ini + 解包成功"的假象，必须直接报错。 */
    if (!index || len == 0) {
        puts("Error: failed to build pak_index.ini (out of memory?)");
        free(index); free(files); return false;
    }
    bool ok = write_file(idxpath, (const uint8_t *)index, len);
    free(index);
    free(files);        /* 仅释放数组；元素 buffer 借入自 buf，由调用方释放 */
    return ok;
}

/* ----------------------------- 打包 ----------------------------- */
static PakFile pack(const uint8_t *idx, uint32_t idxsize, const char *basepath) {
    MyPakHeader h;
    memset(&h, 0, sizeof(h));

    if (!idx || idxsize < sizeof("[Global]") - 1) { puts("Error: Probably broken pak index file."); return NULL_FILE; }

    const char *base = (const char *)idx;
    const char *g = strstr(base, "[Global]");
    if (!g) { puts("Error: Probably broken pak index file."); return NULL_FILE; }

    const char *cur = g + sizeof("[Global]") - 1;
    int consumed = 0;
    if (sscanf(cur, " version=%u%n", &h.version, &consumed) != 1 || consumed == 0) {
        puts("Error: Probably broken pak index file."); return NULL_FILE;
    }
    cur += consumed;
    int e = 0;
    if (sscanf(cur, " encoding=%hhu%n", &h.encoding, &e) == 1) cur += e;

    if (h.version == 5)      h.header_size = PAK_HDR_V5;
    else if (h.version == 4) { h.header_size = PAK_HDR_V4; h.alias_count = 0; }
    else { puts("Error: Unknown pak version."); return NULL_FILE; }

    const char *res = strstr(base, "[Resources]");
    if (!res) { puts("Error: Probably broken pak index file."); return NULL_FILE; }
    const char *alias = strstr(base, "[Alias]");
    const char *resStart = res + sizeof("[Resources]") - 1;
    const char *aliasStart = NULL;
    if (alias && alias > resStart) aliasStart = alias + sizeof("[Alias]") - 1;

    /* v5 下 [Alias] 必须出现在 [Resources] 之后，否则视为损坏（原 D4）。 */
    if (h.version == 5 && alias && alias < resStart) {
        puts("Error: Probably broken pak index file."); return NULL_FILE;
    }

    size_t resRegion = aliasStart ? (size_t)(aliasStart - resStart)
                                  : (idxsize - (size_t)(resStart - base));
    uint32_t resCount = count_char(resStart, resRegion, '=');
    uint32_t aliasDeclared = aliasStart
            ? count_char(aliasStart, idxsize - (size_t)(aliasStart - base), '=')
            : 0;
    /* v4 的头部布局（version(4)+resource_count(4)+encoding(1)）根本没有 alias_count
       字段，别名表无处登记。原工具对此直接报 broken index（rc=8）；重写版一度改成
       "照写但静默丢掉别名"，那是把拒绝换成静默数据丢失（第7周期 D193）。
       差分实测：16 组边界输入里唯一的行为分歧就是这一条。 */
    if (h.version == 4 && aliasDeclared > 0) {
        puts("Error: Probably broken pak index file.");
        return NULL_FILE;
    }
    uint32_t aliasCount = aliasDeclared;
    if (resCount > PAK_MAX16 || aliasCount > PAK_MAX16) {
        puts("Error: Packed pak would exceed 4 GB."); return NULL_FILE;     /* 拒绝截断 */
    }

    PakFile *res_arr = calloc(resCount ? resCount : 1, sizeof(PakFile));
    if (!res_arr) return NULL_FILE;

    const char *r = resStart;
    uint32_t parsed = 0;
    while (parsed < resCount) {
        if (r >= base + idxsize) break;
        uint32_t id = 0;
        char fname[FILENAME_MAX];
        int c = 0;
        fname[0] = '\0';
        /* 宽度限制 %63s 防溢出（原 D2）。 */
        if (sscanf(r, " %u=%63s%n", &id, fname, &c) != 2 || c == 0) {
            puts("Error: Probably broken pak index file.");
            pak_array_free(res_arr, parsed); return NULL_FILE;
        }
        r += c;
        char path[PAK_PATH_MAX];
        int pn = snprintf(path, sizeof(path), "%s/%s", basepath, fname);
        if (pn < 0 || (size_t)pn >= sizeof(path)) {   /* D195：拼接被截断 */
            puts("Error: resource path too long.");
            pak_array_free(res_arr, parsed); return NULL_FILE;
        }
        PakFile f = read_file(path);
        if (!f.buffer) {
            puts("Error: Probably broken pak index file.");
            pak_array_free(res_arr, parsed); return NULL_FILE;
        }
        if (id > PAK_MAX16) {            /* id 是 16 位，拒绝截断 */
            puts("Error: Probably broken pak index file.");
            free(f.buffer); pak_array_free(res_arr, parsed); return NULL_FILE;
        }
        f.id = (uint16_t)id;
        res_arr[parsed++] = f;
    }
    h.resource_count = parsed;

    uint16_t *aids = NULL, *aidx = NULL;
    uint16_t aliasCount16 = (uint16_t)aliasCount;
    if (aliasCount > 0) {
        aids = malloc((size_t)aliasCount * sizeof(uint16_t));
        aidx = malloc((size_t)aliasCount * sizeof(uint16_t));
        if (!aids || !aidx) {
            free(aids); free(aidx); pak_array_free(res_arr, parsed); return NULL_FILE;
        }
        const char *a = aliasStart;
        uint32_t ap = 0;
        while (ap < aliasCount) {
            uint16_t rid = 0, eix = 0;
            int c2 = 0;
            if (a >= base + idxsize) break;
            if (sscanf(a, " %hu=%hu%n", &rid, &eix, &c2) != 2 || c2 == 0) {
                puts("Error: Probably broken pak index file.");
                free(aids); free(aidx); pak_array_free(res_arr, parsed); return NULL_FILE;
            }
            if (eix >= h.resource_count) {   /* 别名必须引用真实资源条目 */
                puts("Error: Probably broken pak index file.");
                free(aids); free(aidx); pak_array_free(res_arr, parsed); return NULL_FILE;
            }
            a += c2;
            aids[ap] = rid; aidx[ap] = eix; ap++;
        }
    }

    PakFile out = pack_files(&h, res_arr, aids, aidx, aliasCount16);
    pak_array_free(res_arr, parsed);   /* 释放源文件缓冲（pack_files 已 memcpy 副本） */
    free(aids); free(aidx);
    return out;
}

/* ----------------------------- CLI ----------------------------- */
int main(int argc, char *argv[]) {
    uint32_t flags = 0;
#define F_HELP 0
#define F_UNPACK 1
#define F_PACK 2
#define F_VERSION 3
#define F_ASCII 4

    char path1[PAK_PATH_MAX];
    char path2[PAK_PATH_MAX];
    memset(path1, 0, sizeof(path1));
    memset(path2, 0, sizeof(path2));

    for (int i = 1; i < argc; i++) {
        char *arg = argv[i];
        bool isConfig = false;
        if (*arg != '\0' && (*arg == '/' || *arg == '-')) { arg++; isConfig = true; }
        if (!isConfig) continue;
        switch (*arg) {
            case 'h': flags = F_HELP; break;
            case 'a': case 'p': flags = F_PACK; break;
            case 'u': case 'e': case 'x': flags = F_UNPACK; break;
            case 'v': flags = F_VERSION; break;
            case 'c': flags = F_ASCII; break;
        }
        if ((flags == F_UNPACK || flags == F_PACK) && i + 2 < argc) {
            /* D7：先拒绝超长路径，再受控拷贝，绝不溢出固定缓冲。 */
            if (strlen(argv[i + 1]) >= PAK_PATH_MAX ||
                strlen(argv[i + 2]) >= PAK_PATH_MAX) {
                printf("Error: path argument too long (>= %d)\n", (int)PAK_PATH_MAX);
                return 33;
            }
            snprintf(path1, sizeof(path1), "%s", argv[i + 1]);
            snprintf(path2, sizeof(path2), "%s", argv[i + 2]);
            i += 2;
        }
    }

    if (flags == F_VERSION) { printf("Pak v2.0.2 (modern safe build)\n"); return 0; }
    if (flags == F_HELP) {
        printf("\nPak v2.0.2 - Pack/Unpack Chromium .pak files.\n\n");
        printf("Usage:\n");
        printf("  -u <file.pak> <out_dir>      Unpack a .pak file.\n");
        printf("  -p <pak_index.ini> <out.pak> Re-pack from an index file.\n");
        printf("  -v  Print version.   -h  Print this help.   -c  Print a notice.\n");
        printf("Note: Existing destination files will be overwritten!\n");
        return 0;
    }
    if (flags == F_ASCII) { printf("\n  Long Live Chromium\n\n"); return 0; }

    if (flags == F_UNPACK) {
        PakFile pf = read_file(path1);
        if (pf.buffer == NULL) { printf("Error: Cannot read .pak file %s\n", path1); return 1; }
        if (!check_format(pf.buffer, pf.size)) { free(pf.buffer); return 2; }
        bool ok = unpack(pf.buffer, pf.size, path2);
        free(pf.buffer);
        if (!ok) { printf("Error: Unpack failed.\n"); return 4; }
        printf("Unpacked %s to %s\n\n", path1, path2);
        return 0;
    } else if (flags == F_PACK) {
        PakFile idx = read_file(path1);
        if (idx.buffer == NULL) { printf("Error: Cannot read pak index file %s\n", path1); return 6; }
        /* 取索引文件所在目录作为资源基路径（无分隔符时回退为空串）。 */
        char basepath[PAK_PATH_MAX];
        memset(basepath, 0, sizeof(basepath));
        const char *sep = strrchr(path1, '\\');
        if (!sep) sep = strrchr(path1, '/');
        if (sep && sep > path1) {
            size_t n = (size_t)(sep - path1);
            if (n < sizeof(basepath)) { memcpy(basepath, path1, n); basepath[n] = '\0'; }
        }
        PakFile out = pack(idx.buffer, idx.size, basepath);
        free(idx.buffer);
        if (out.buffer == NULL) return 8;
        if (!write_file(path2, out.buffer, out.size)) {
            printf("Error: Cannot write to %s\n", path2); free(out.buffer); return 9;
        }
        free(out.buffer);
        printf("\nPacked %s\n\n", path2);
        return 0;
    }

    printf("No valid flag. Use -h for help.\n");
    return 32;
}
