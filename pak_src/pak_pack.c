#include "pak_pack.h"
#include <stdarg.h>

// Grows the index-string buffer until at least `need` bytes are free after
// `offset`. Always returns the live buffer pointer (unchanged on failure),
// so callers must assign the result back; a later bounded append then fails
// cleanly instead of writing into a freed/reallocated region.
static char *pakIndexReserve(char *buffer, uint32_t *length, uint32_t offset,
                             uint32_t need) {
    while (*length < offset + need) {
        uint32_t newLength = *length + PAK_BUFFER_BLOCK_SIZE;
        if (newLength <= *length) // overflow guard
            return buffer;
        char *grown = realloc(buffer, newLength);
        if (grown == NULL)
            return buffer; // keep the old buffer alive; append will refuse
        buffer = grown;
        *length = newLength;
    }
    return buffer;
}

// Bounded append into the index-string buffer. Returns bytes written, or 0
// when there was not enough reserved room (caller must Reserve first).
static uint32_t pakIndexAppend(char *buffer, uint32_t capacity,
                               uint32_t offset, const char *format, ...) {
    if (capacity <= offset)
        return 0;
    va_list args;
    va_start(args, format);
    int written = vsnprintf(buffer + offset, (size_t)(capacity - offset),
                            format, args);
    va_end(args);
    if (written < 0 || (uint32_t)written > capacity - offset)
        return 0;
    return (uint32_t)written;
}

bool pakUnpack(uint8_t *buffer, unsigned int size, char *outputPath) {
    MyPakHeader myHeader;
    if (!pakParseHeader(buffer, size, &myHeader)) {
        return false;
    }
    uint64_t tableSize =
        (uint64_t)myHeader.size +
        ((uint64_t)myHeader.resource_count + 1) * PAK_ENTRY_SIZE +
        (uint64_t)myHeader.alias_count * PAK_ALIAS_SIZE;
    if (tableSize > (uint64_t)size) {
        puts(PAK_ERROR_TRUNCATED);
        return false;
    }
    PakFile *files = pakGetFiles(buffer, size);
    if (files == NULL) {
        return false;
    }

    char fileNameBuf[FILENAME_MAX];
    memset(fileNameBuf, 0, sizeof(fileNameBuf));
    char pathBuf[PATH_MAX];
    memset(pathBuf, 0, sizeof(pathBuf));

#ifdef _WIN32
    CreateDirectory(outputPath, NULL);
#else
    mkdir(outputPath, 0777);
#endif
    uint32_t length = PAK_BUFFER_BLOCK_SIZE;
    char *pakIndexStr = calloc(length, sizeof(char));
    if (pakIndexStr == NULL) {
        free(files);
        return false;
    }
    uint32_t offset = 0;
    // Global header lines. The Reserve result MUST be assigned back
    // (realloc may move the buffer).
    pakIndexStr = pakIndexReserve(pakIndexStr, &length, offset,
                                  PAK_BUFFER_MIN_FREE_SIZE);
    if (pakIndexAppend(pakIndexStr, length, offset,
                       PAK_INDEX_GLOBAL_TAG "\r\nversion=%u\r\n",
                       myHeader.version) == 0) {
        goto UNPACK_FAIL;
    }
    offset = (uint32_t)strlen(pakIndexStr);
    pakIndexStr = pakIndexReserve(pakIndexStr, &length, offset,
                                  PAK_BUFFER_MIN_FREE_SIZE);
    if (pakIndexAppend(pakIndexStr, length, offset,
                       "encoding=%u\r\n\r\n" PAK_INDEX_RES_TAG "\r\n",
                       myHeader.encoding) == 0) {
        goto UNPACK_FAIL;
    }
    offset = (uint32_t)strlen(pakIndexStr);
    for (uint32_t i = 0; i < myHeader.resource_count; i++) {
        int nameLen = _snprintf(fileNameBuf, sizeof(fileNameBuf), "%u%s",
                                files[i].id, pakGetFileType(files[i]));
        if (nameLen < 0 || (size_t)nameLen >= sizeof(fileNameBuf)) {
            goto UNPACK_FAIL;
        }
        pakIndexStr = pakIndexReserve(pakIndexStr, &length, offset,
                                      PAK_BUFFER_MIN_FREE_SIZE);
        if (pakIndexAppend(pakIndexStr, length, offset, "%u=%s\r\n",
                           files[i].id, fileNameBuf) == 0) {
            goto UNPACK_FAIL;
        }
        offset = (uint32_t)strlen(pakIndexStr);
        // Defect D10: bounded path composition instead of unbounded sprintf
        int p = _snprintf(pathBuf, sizeof(pathBuf), "%s/%s", outputPath,
                          fileNameBuf);
        if (p < 0 || (size_t)p >= sizeof(pathBuf)) {
            goto UNPACK_FAIL;
        }
        // Defect D17: propagate per-resource write failures
        if (!writeFile(pathBuf, files[i])) {
            goto UNPACK_FAIL;
        }
    }
    if (myHeader.alias_count > 0) {
        pakIndexStr = pakIndexReserve(pakIndexStr, &length, offset,
                                      PAK_BUFFER_MIN_FREE_SIZE);
        if (pakIndexAppend(pakIndexStr, length, offset,
                           "\r\n" PAK_INDEX_ALIAS_TAG "\r\n") == 0) {
            goto UNPACK_FAIL;
        }
        offset = (uint32_t)strlen(pakIndexStr);
    }
    PakAlias *aliasBuf = NULL;
    if (myHeader.alias_count > 0) {
        aliasBuf =
            (PakAlias *)(buffer + myHeader.size +
                        (myHeader.resource_count + 1) * PAK_ENTRY_SIZE);
    }
    for (uint32_t i = 0; i < myHeader.alias_count; i++) {
        pakIndexStr = pakIndexReserve(pakIndexStr, &length, offset,
                                      PAK_BUFFER_MIN_FREE_SIZE);
        if (pakIndexAppend(pakIndexStr, length, offset, "%u=%u\r\n",
                           aliasBuf->resource_id, aliasBuf->entry_index) == 0) {
            goto UNPACK_FAIL;
        }
        offset = (uint32_t)strlen(pakIndexStr);
        aliasBuf++;
    }
    char idxPath[PATH_MAX];
    int idxLen = _snprintf(idxPath, sizeof(idxPath), "%s/pak_index.ini", outputPath);
    if (idxLen < 0 || (size_t)idxLen >= sizeof(idxPath)) {
        goto UNPACK_FAIL;
    }
    PakFile pakIndexBuf;
    pakIndexBuf.buffer = pakIndexStr;
    pakIndexBuf.size = offset;
    bool indexWritten = writeFile(idxPath, pakIndexBuf);
    free(pakIndexStr);
    free(files);
    return indexWritten;

UNPACK_FAIL:
    free(pakIndexStr);
    free(files);
    return false;
}

uint32_t countChar(const char *string, uint32_t length, char toCount) {
    uint32_t count = 0;
    for (uint32_t i = 0; i < length; i++) {
        if (string[i] == toCount)
            count++;
    }
    return count;
}

PakFile pakPack(PakFile pakIndex, char *path) {
    MyPakHeader myHeader;
    memset(&myHeader, 0, sizeof(myHeader));
    PakFile pakFile = NULL_File;
    PakFile *resFiles = NULL;
    PakAlias *pakAlias = NULL;

    char *pakIndexBuf = pakIndex.buffer;
    uint32_t count = 0;
    int matched;

    // Defect D4/D18: the buffer must at least contain "[Global]" + NUL,
    // otherwise every offset below runs away.
    if (pakIndexBuf == NULL || pakIndex.size < sizeof(PAK_INDEX_GLOBAL_TAG)) {
        puts(PAK_ERROR_BROKEN_INDEX);
        goto PAK_PACK_END;
    }

    uint32_t offset = (uint32_t)(sizeof(PAK_INDEX_GLOBAL_TAG) - 1);
    matched = sscanf(pakIndexBuf + offset, " version=%u%n",
                     &myHeader.version, &count);
    if (matched != 1 || count == 0) {
        puts(PAK_ERROR_BROKEN_INDEX);
        goto PAK_PACK_END;
    }
    offset += (uint32_t)count;

    count = 0;
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wformat"
#pragma GCC diagnostic ignored "-Wformat-extra-args"
    matched = sscanf(pakIndexBuf + offset, " encoding=%hhu%n",
                     &myHeader.encoding, &count);
#pragma GCC diagnostic pop
    if (count > 0)
        offset += (uint32_t)count;

    if (myHeader.version == 5) {
        myHeader.size = PAK_HEADER_SIZE_V5;
    } else if (myHeader.version == 4) {
        myHeader.size = PAK_HEADER_SIZE_V4;
    } else {
        puts(PAK_ERROR_UNKNOWN_VER);
        goto PAK_PACK_END;
    }

    char *pakIndexEnd = pakIndexBuf + pakIndex.size - 1;
    // Defect D4: [Resources] section is mandatory; validate every section
    // pointer stays inside the buffer and sections appear in order.
    char *pakResTagPos = strstr(pakIndexBuf, PAK_INDEX_RES_TAG);
    if (pakResTagPos == NULL || pakResTagPos > pakIndexEnd) {
        puts(PAK_ERROR_BROKEN_INDEX);
        goto PAK_PACK_END;
    }
    char *pakEntryIndex = pakResTagPos + (sizeof(PAK_INDEX_RES_TAG) - 1);
    if (pakEntryIndex > pakIndexEnd)
        pakEntryIndex = pakIndexEnd;

    char *pakAliasIndex = strstr(pakIndexBuf, PAK_INDEX_ALIAS_TAG);
    uint32_t aliasCountRaw = 0;
    if (myHeader.version == 4 || pakAliasIndex == NULL ||
        pakAliasIndex < pakEntryIndex) {
        if (myHeader.version == 5 && pakAliasIndex != NULL &&
            pakAliasIndex < pakEntryIndex) {
            puts(PAK_ERROR_BROKEN_INDEX);
            goto PAK_PACK_END;
        }
        myHeader.alias_count = 0;
        pakAliasIndex = pakIndexEnd;
    } else {
        pakAliasIndex += (sizeof(PAK_INDEX_ALIAS_TAG) - 1);
        if (pakAliasIndex > pakIndexEnd) {
            puts(PAK_ERROR_BROKEN_INDEX);
            goto PAK_PACK_END;
        }
        aliasCountRaw =
            countChar(pakAliasIndex, (uint32_t)(pakIndexEnd - pakAliasIndex), '=');
        if (aliasCountRaw > 0xFFFF) {
            puts(PAK_ERROR_TOO_LARGE);
            goto PAK_PACK_END;
        }
        myHeader.alias_count = (uint16_t)aliasCountRaw;
    }
    uint32_t resCount =
        countChar(pakEntryIndex, (uint32_t)(pakAliasIndex - pakEntryIndex), '=');
    // v5 header stores counts in 16-bit fields; refuse silent truncation.
    if (resCount > 0xFFFF) {
        puts(PAK_ERROR_TOO_LARGE);
        goto PAK_PACK_END;
    }
    myHeader.resource_count = resCount;

    char fileNameBuf[FILENAME_MAX];
    memset(fileNameBuf, 0, sizeof(fileNameBuf));
    char pathBuf[PATH_MAX];
    memset(pathBuf, 0, sizeof(pathBuf));
    resFiles = calloc(myHeader.resource_count, sizeof(PakFile));
    if (resFiles == NULL) {
        goto PAK_PACK_END;
    }

    offset = 0;
    for (uint32_t i = 0; i < myHeader.resource_count; i++) {
        uint32_t id = 0;
        count = 0;
        fileNameBuf[0] = '\0';
        // Defect D2: width-limited string capture (%255s into 260-byte buf)
        matched = sscanf(pakEntryIndex + offset, " %u=%255s%n", &id,
                         fileNameBuf, &count);
        if (matched != 2 || count == 0) {
            puts(PAK_ERROR_BROKEN_INDEX);
            myHeader.resource_count = i;
            goto PAK_PACK_END;
        }
        offset += (uint32_t)count;
        // Defect D10: bounded path composition
        int p = _snprintf(pathBuf, sizeof(pathBuf), "%s%s", path, fileNameBuf);
        if (p < 0 || (size_t)p >= sizeof(pathBuf)) {
            puts(PAK_ERROR_BROKEN_INDEX);
            myHeader.resource_count = i;
            goto PAK_PACK_END;
        }
        resFiles[i] = readFile(pathBuf);
        if (resFiles[i].buffer == NULL) {
            puts(PAK_ERROR_BROKEN_INDEX);
            myHeader.resource_count = i;
            goto PAK_PACK_END;
        }
        if (id > 0xFFFF) { // ids are 16-bit on disk; refuse truncation
            puts(PAK_ERROR_BROKEN_INDEX);
            myHeader.resource_count = i;
            goto PAK_PACK_END;
        }
        resFiles[i].id = (uint16_t) id;
    }
    if (myHeader.alias_count > 0) {
        offset = 0;
        pakAlias = calloc(myHeader.alias_count, sizeof(PakAlias));
        if (pakAlias == NULL) {
            goto PAK_PACK_END;
        }
        for (uint32_t i = 0; i < myHeader.alias_count; i++) {
            count = 0;
            matched = sscanf(pakAliasIndex + offset, " %hu=%hu%n",
                             &pakAlias[i].resource_id,
                             &pakAlias[i].entry_index, &count);
            if (matched != 2 || count == 0) {
                puts(PAK_ERROR_BROKEN_INDEX);
                goto PAK_PACK_END;
            }
            // An alias must reference a real resource entry.
            if (pakAlias[i].entry_index >= myHeader.resource_count) {
                puts(PAK_ERROR_BROKEN_INDEX);
                goto PAK_PACK_END;
            }
            offset += (uint32_t)count;
        }
    }
    pakFile = pakPackFiles(&myHeader, resFiles, pakAlias);
    printf("\nresource_count = %u\nalias_count = %u\n", myHeader.resource_count,
           myHeader.alias_count);
    printf("version = %u\nencoding = %u\n", myHeader.version, myHeader.encoding);
    printf("\n.pak size: %u", pakFile.size);
    printf(" bytes\n");
PAK_PACK_END:
    if (resFiles != NULL) {
        for (uint32_t i = 0; i < myHeader.resource_count; i++) {
            if (resFiles[i].buffer != NULL)
                free(resFiles[i].buffer);
        }
        free(resFiles);
    }
    if (pakAlias != NULL)
        free(pakAlias);
    return pakFile;
}
