#include "pak_header.h"

bool pakParseHeader(void *buffer, unsigned int size, MyPakHeader *myHeader) {
    memset(myHeader, 0, sizeof(MyPakHeader));
    if (buffer == NULL || size < 4) {
        puts(PAK_ERROR_TRUNCATED);
        return false;
    }
    myHeader->version = pakGetVerison(buffer);
    if (myHeader->version == 5) {
        if (size < sizeof(PakHeaderV5)) {
            puts(PAK_ERROR_TRUNCATED);
            return false;
        }
        PakHeaderV5 *header = (PakHeaderV5 *)buffer;
        myHeader->resource_count = header->resource_count;
        myHeader->encoding = header->encoding;
        myHeader->alias_count = header->alias_count;
        myHeader->size = PAK_HEADER_SIZE_V5;
    } else if (myHeader->version == 4) {
        if (size < sizeof(PakHeaderV4)) {
            puts(PAK_ERROR_TRUNCATED);
            return false;
        }
        PakHeaderV4 *header = (PakHeaderV4 *)buffer;
        myHeader->resource_count = header->resource_count;
        myHeader->encoding = header->encoding;
        myHeader->alias_count = 0;
        myHeader->size = PAK_HEADER_SIZE_V4;
    } else {
        puts(PAK_ERROR_UNKNOWN_VER);
        return false;
    }
    return true;
}

unsigned int pakWriteHeader(MyPakHeader *myHeader, void *buffer) {
    if (buffer == NULL || myHeader == NULL)
        return 0;
    if (myHeader->version == 5) {
        PakHeaderV5 *header = (PakHeaderV5 *)buffer;
        header->version = myHeader->version;
        header->resource_count = (uint16_t) myHeader->resource_count;
        header->encoding = myHeader->encoding;
        header->alias_count = myHeader->alias_count;
    } else if (myHeader->version == 4) {
        PakHeaderV4 *header = (PakHeaderV4 *)buffer;
        header->version = myHeader->version;
        header->resource_count = myHeader->resource_count;
        header->encoding = myHeader->encoding;
    } else {
        puts(PAK_ERROR_UNKNOWN_VER);
        return 0;
    }
    return myHeader->size;
}

bool pakCheckFormat(uint8_t *buffer, unsigned int size) {
    MyPakHeader myHeader;
    if (!pakParseHeader(buffer, size, &myHeader)) {
        return false;
    }
    // 64-bit arithmetic: a crafted (huge) resource_count must fail the
    // comparison instead of wrapping around a 32-bit sum.
    uint64_t tableSize =
        (uint64_t)myHeader.size +
        ((uint64_t)myHeader.resource_count + 1) * PAK_ENTRY_SIZE +
        (uint64_t)myHeader.alias_count * PAK_ALIAS_SIZE;
    if (tableSize > (uint64_t)size) {
        puts(PAK_ERROR_TRUNCATED);
        return false;
    }
    PakEntry *entryPtr = (PakEntry *)(buffer + myHeader.size);
    uint32_t previousOffset = 0;
    for (unsigned int i = 0; i <= myHeader.resource_count; i++) {
        uint32_t offset = entryPtr->offset;
        if (size < offset) {
            puts(PAK_ERROR_TRUNCATED);
            return false;
        }
        // Chromium pak entry tables are strictly ordered by offset; a
        // non-monotonic table would produce wrapped (huge) resource sizes
        // downstream, so reject it here. Entry 0 is the terminating entry
        // and does not have a predecessor to compare against.
        if (i > 0 && offset < previousOffset) {
            puts(PAK_ERROR_BAD_ENTRY_ORDER);
            return false;
        }
        previousOffset = offset;
        entryPtr++;
    }
    return true;
}
