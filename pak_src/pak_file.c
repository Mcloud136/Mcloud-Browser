#include "pak_file.h"

// Verify header + entry table + alias table all fit inside `size` bytes.
static bool pakTablesInRange(MyPakHeader *myHeader, unsigned int size) {
    uint64_t tableSize =
        (uint64_t)myHeader->size +
        ((uint64_t)myHeader->resource_count + 1) * PAK_ENTRY_SIZE +
        (uint64_t)myHeader->alias_count * PAK_ALIAS_SIZE;
    return tableSize <= (uint64_t)size;
}

PakFile pakPackFiles(MyPakHeader *myHeader, PakFile *pakResFile,
                    PakAlias *pakAlias) {
    // resource_count == 0 used to read (pakResFile - 1) out of bounds and
    // memcpy(dst, NULL, 0) was undefined behaviour (defect D3).
    if (myHeader == NULL || pakResFile == NULL ||
        myHeader->resource_count == 0) {
        return NULL_File;
    }
    // Sum every size in 64-bit and refuse >4G output: a wrapped 32-bit sum
    // would under-allocate the buffer and let the copy loop write OOB
    // (defect D5).
    uint64_t size = myHeader->size;
    uint64_t entrySize =
        ((uint64_t)myHeader->resource_count + 1) * PAK_ENTRY_SIZE;
    uint64_t aliasSize = (uint64_t)myHeader->alias_count * PAK_ALIAS_SIZE;
    for (uint32_t i = 0; i < myHeader->resource_count; i++) {
        size += (pakResFile + i)->size;
    }
    size += entrySize + aliasSize;
    if (size > 0xFFFFFFFFull) {
        puts(PAK_ERROR_TOO_LARGE);
        return NULL_File;
    }
    uint8_t *buffer = calloc((uint32_t)size, sizeof(uint8_t));
    if (buffer == NULL)
        return NULL_File;
    uint32_t offset = pakWriteHeader(myHeader, buffer);
    if (offset == 0) {
        free(buffer);
        return NULL_File;
    }

    PakEntry *enrtyPtr = (PakEntry *)(buffer + offset);
    uint8_t *filePtr = buffer + offset + entrySize + aliasSize;
    uint8_t *bufferEnd = buffer + (uint32_t)size;
    for (uint32_t i = 0; i < myHeader->resource_count; i++) {
        // Defensive: the computed total must cover every payload byte.
        if (filePtr + pakResFile[i].size > bufferEnd) {
            free(buffer);
            return NULL_File;
        }
        memcpy(filePtr, pakResFile[i].buffer, pakResFile[i].size);
        enrtyPtr->resource_id = pakResFile[i].id;
        enrtyPtr->offset = (uint32_t)(filePtr - buffer);
        filePtr += pakResFile[i].size;
        enrtyPtr++;
    }

    // Terminating entry. resource_count >= 1 is guaranteed above, so the end
    // of payload is a valid sentinel offset.
    enrtyPtr->resource_id = 0;
    enrtyPtr->offset = (uint32_t)(filePtr - buffer);

    if (aliasSize > 0 && pakAlias != NULL) {
        memcpy((void *)(enrtyPtr + 1), pakAlias, (size_t)aliasSize);
    }
    PakFile pakFile;
    pakFile.buffer = buffer;
    pakFile.size = (uint32_t)size;
    return pakFile;
}

PakFile pakGetFile(uint8_t *pakBuffer, unsigned int size, uint16_t id) {
    PakFile pakFile = NULL_File;
    MyPakHeader myHeader;
    if (!pakParseHeader(pakBuffer, size, &myHeader)) {
        return NULL_File;
    }
    if (!pakTablesInRange(&myHeader, size)) {
        return NULL_File;
    }
    PakEntry *entries = (PakEntry *)(pakBuffer + myHeader.size);
    if (myHeader.version == 5) {
        PakAlias *aliasPtr =
            (PakAlias *)(pakBuffer + myHeader.size +
                         (myHeader.resource_count + 1) * PAK_ENTRY_SIZE);
        for (uint16_t i = 0; i < myHeader.alias_count; i++) {
            if (aliasPtr->resource_id == id) {
                // entry_index must reference a real entry whose successor
                // (the sentinel-adjacent next row) exists.
                if (aliasPtr->entry_index >= myHeader.resource_count) {
                    return NULL_File;
                }
                PakEntry *target = entries + aliasPtr->entry_index;
                if (target->offset > size || (target + 1)->offset > size ||
                    (target + 1)->offset < target->offset) {
                    return NULL_File;
                }
                pakFile.buffer = pakBuffer + target->offset;
                pakFile.size = (target + 1)->offset - target->offset;
                return pakFile;
            }
            // Advance the cursor: the original loop re-checked the first
            // alias forever (defect D15).
            aliasPtr++;
        }
    }
    for (uint32_t i = 0; i < myHeader.resource_count; i++) {
        if (entries[i].resource_id == id) {
            if (entries[i].offset > size || entries[i + 1].offset > size ||
                entries[i + 1].offset < entries[i].offset) {
                return NULL_File;
            }
            pakFile.buffer = pakBuffer + entries[i].offset;
            pakFile.size = entries[i + 1].offset - entries[i].offset;
            return pakFile;
        }
    }
    return NULL_File;
}

PakFile *pakGetFiles(uint8_t *buffer, unsigned int size) {
    PakFile *pakResFile = NULL;
    MyPakHeader myHeader;
    if (!pakParseHeader(buffer, size, &myHeader)) {
        return NULL;
    }
    if (!pakTablesInRange(&myHeader, size)) {
        return NULL;
    }
    pakResFile = (PakFile *)calloc(myHeader.resource_count, sizeof(PakFile));
    PakFile *returnValue = pakResFile;
    if (pakResFile == NULL) {
        return NULL;
    }
    PakEntry *pakEntryPtr = (PakEntry *)(buffer + myHeader.size);
    for (uint32_t i = 0; i < myHeader.resource_count; i++) {
        uint32_t offset = pakEntryPtr->offset;
        uint32_t nextOffset = (pakEntryPtr + 1)->offset;
        // Reject out-of-range or non-monotonic tables instead of handing
        // wrapped (huge) sizes to writeFile (defects D5/D1).
        if (offset > size || nextOffset > size || nextOffset < offset) {
            free(returnValue);
            return NULL;
        }
        pakResFile->id = pakEntryPtr->resource_id;
        pakResFile->buffer = buffer + offset;
        pakResFile->size = nextOffset - offset;
        pakEntryPtr++;
        pakResFile++;
    }
    return returnValue;
}
