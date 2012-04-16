#!/usr/bin/env python
# Copyright (c) 2012 Hung-Te Lin <piaip@csie.ntu.edu.tw>. All rights reserved.
# Use of this source code is governed by a BSD license.

"""
brcstored: Board RC (brc) storage daemon.

Provides a way to manage per-user BRC object into isolated database.
"""

import StringIO
import logging
import re
import sys
import leveldb
import eventlet
import struct


_SERVER_ADDR = '127.0.0.1'
_SERVER_PORT = 5133
_DB_PATH = '/home/bbs/brcstore/database'


def get_data(uid):
    try:
        return g_db.Get(uid)
    except KeyError:
        return None


def put_data(uid, blob):
    g_db.Put(uid, blob)


def open_database(db_path):
    global g_db
    # BRCv3 max size = 49152 (8192*3*2), so let's increase block size.
    # LevelDB default I/O buffer size: R=8M, W=2M.
    g_db = leveldb.LevelDB(db_path, block_size=49152,
            block_cache_size=(16 * (2 << 20)),
            write_buffer_size=(16 * (2 << 20)))


def handle_request(sock, fd):
    # WRITE: 'w' + UID + '\n' + int32_t len, BYTE[len]
    # READ: 'r' + UID + '\n'
    #  Returns: int32_t len, BYTE[len]   (len=-1 if UID does not exist)
    fmt_len = '@i'
    try:
        command = fd.read(1)
        uid = fd.readline().strip()
        if command == 'r':
            msg = get_data(uid)
            if msg is None:
                fd.write(struct.pack(fmt_len, -1))
                logging.info('Read : %s: (NOT FOUND)', uid)
            else:
                fd.write(struct.pack(fmt_len, len(msg)))
                fd.write(msg)
                logging.info('Read : %s: size=%d', uid, len(msg))
        elif command == 'w':
            msglen = struct.unpack(fmt_len,
                                   fd.read(struct.calcsize(fmt_len)))[0]
            msg = fd.read(msglen)
            logging.info('Write: %s: size=%d', uid, len(msg))
            put_data(uid, msg)
        elif not command:
            raise ValueError('Incomplete request (no command).')
        else:
            raise ValueError('Unknown request: 0x%02X' % ord(command))
    except:
        logging.exception("handle_request")
    finally:
        try:
            fd.close()
            sock.close()
        except:
            pass


def main(myname, argv):
    level = logging.WARNING
    # level = logging.INFO
    # level = logging.DEBUG
    logging.basicConfig(level=level, format='%(asctime)-15s %(message)s')
    if len(argv) not in [0, 1]:
        print "Usage: %s [db_path]" % myname
        exit(1)
    db_path = argv[0] if len(argv) > 0 else _DB_PATH
    logging.warn("Serving at %s:%s [db:%s]...", _SERVER_ADDR, _SERVER_PORT,
                 db_path)
    open_database(db_path)
    server = eventlet.listen((_SERVER_ADDR, _SERVER_PORT))
    pool = eventlet.GreenPool()
    while True:
        try:
            new_sock, address = server.accept()
            pool.spawn_n(handle_request, new_sock, new_sock.makefile('rw'))
        except (SystemExit, KeyboardInterrupt):
            break


if __name__ == '__main__':
    main(sys.argv[0], sys.argv[1:])