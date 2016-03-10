import sys
import os.path as path
# add the parent directory
sys.path.append(path.dirname(path.dirname(path.realpath(__file__))))
import nbt
import mclevel
import shutil

# this may come in useful in the future
class DebuggerBytesIO(io.BytesIO):
    def write(self, *args):
        super().write(*args)
        # fail if the buffer grows beyond 10mb, a reasonable size for a
        # Minecraft region file
        assert self.tell() < (5 * 1024 * 1024)

def read():
    path = 'nbt\\region\\r.0.0.mca'
    with open(path, mode='rb') as file:
        header = mclevel.readRegionHeader(0, 0, file)
        offset, size, timestamp = header.getChunk(0, 0)
        chunkTag = mclevel.readChunk(offset, size, file)
    chunk = mclevel.parseChunkNbt(chunkTag)
    print(offset, size)
    nbt.tagToJson('json', 'chunk.nbt', chunkTag)
    
def write():
    chunk = nbt.fromJson('', 'json/chunk.nbt.json', 'json/chunk.tagtypes.json')
    
    # make sure we are operating on a clean (noncorrupt) file
    shutil.copy2('nbt/region/r.0.0.mca', 'gen/r.0.0.mca')
    # write the data
    with open('gen/r.0.0.mca', mode='r+b') as file:
        header = mclevel.RegionHeader(0, 0, file)
        mclevel.writeChunk(chunk, file, header)

#read()
write()
# TODO: make it work. write now it corrupts the file...