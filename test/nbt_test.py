import sys
import os.path as path
# add the parent directory
sys.path.append(path.dirname(path.dirname(path.realpath(__file__))))
import nbt
import io
import gzip

def read():
    nbt.toJson('nbt/level.dat', 'json', gzipped=False)

def write():
    level = nbt.fromJson('', 'json/level.dat.json', 'json/level.tagtypes.json')

    stream = io.BytesIO()
    writer = nbt.NbtWriter(stream)
    writer.write(level)
    stream.seek(0)
    with open('out.dat', mode='wb') as file:
       file.write(gzip.compress(stream.read()))
       
write()