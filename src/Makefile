CC = gcc
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -O2
PYTHON ?= python3

.PHONY: all clean test

all: gsh

gsh: gsh.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LDLIBS)

test: gsh
	cd .. && $(PYTHON) -m unittest discover -s tests -v

clean:
	rm -f gsh
