CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Wpedantic -O2
BIN     ?= pak

all: $(BIN)

$(BIN): pak.c
	$(CC) $(CFLAGS) pak.c -o $(BIN)

test: $(BIN)
	sh ./run_test.sh

clean:
	rm -f $(BIN) $(BIN).exe
	rm -rf t_out_build

.PHONY: all test clean
