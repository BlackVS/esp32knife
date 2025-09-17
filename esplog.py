#!/usr/bin/env python3

FILE_LOG = None

def printlog(*args, **kwargs):
    global FILE_LOG
    print(*args, **kwargs)
    if FILE_LOG:
        kwargs['file']=FILE_LOG
        print(*args, **kwargs)


def log(f, txt=""):
    printlog(txt)
    f.write( "{}\n".format(txt))

def log_open(fname=""):
    global FILE_LOG
    FILE_LOG = open(fname, "wt")

def log_close():
    global FILE_LOG
    if FILE_LOG:
        FILE_LOG.close()
        FILE_LOG = None