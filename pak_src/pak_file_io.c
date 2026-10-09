#include "pak_file_io.h"

PakFile readFile(const char *fileName) {
    PakFile file = NULL_File;
    /* declare a file pointer */
    FILE *filePtr = fopen(fileName, "rb");
    /* quit if the file does not exist */
    if (filePtr == NULL)
        return NULL_File;

    /* Get the number of bytes; reject seek failures and >4G files
       (defect D6/D16: unchecked ftell, silent 32-bit truncation) */
    if (fseeko(filePtr, 0, SEEK_END) != 0) {
        fclose(filePtr);
        return NULL_File;
    }
    int64_t length = ftello(filePtr);
    if (length < 0 || length > (int64_t)UINT32_MAX - 1) {
        fclose(filePtr);
        return NULL_File;
    }

    /* reset the file position indicator to
    the beginning of the file */
    if (fseeko(filePtr, 0, SEEK_SET) != 0) {
        fclose(filePtr);
        return NULL_File;
    }

    file.size = (uint32_t)length;

    /* grab sufficient memory for the
    buffer to hold the text */
    file.buffer = calloc(file.size + 1, sizeof(uint8_t));

    /* memory error: close the handle before returning (defect D6:
       the original leaked filePtr here) */
    if (file.buffer == NULL) {
        fclose(filePtr);
        return NULL_File;
    }

    /* copy all the text into the buffer; a short read is a hard error,
       not silent data corruption (defect D6) */
    if (file.size > 0 &&
        fread(file.buffer, sizeof(uint8_t), file.size, filePtr) !=
            file.size) {
        free(file.buffer);
        file.buffer = NULL;
        fclose(filePtr);
        return NULL_File;
    }
    fclose(filePtr);

    return file;
}

bool writeFile(const char *fileName, const PakFile file) {
    FILE *filePtr = fopen(fileName, "wb");
    if (filePtr == NULL)
        return false;
    const size_t result = fwrite(file.buffer, sizeof(uint8_t), file.size, filePtr);
    fclose(filePtr);
    return (result == file.size);
}
