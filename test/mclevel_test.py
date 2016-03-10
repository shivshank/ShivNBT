import sys
import os.path as path
import shutil
import io
# add the parent directory
sys.path.append(path.dirname(path.dirname(path.realpath(__file__))))
import nbt
import mclevel

def readIntoJSON(x, z):
    print('# Reading demo #')
    rx, rz = mclevel.getRegionPos(x, z)
    path = 'nbt/region/r.' + str(rx) + '.' + str(rz) + '.mca'
    with open(path, mode='rb') as file:
        header = mclevel.RegionHeader(rx, rz, file)
        offset, size, timestamp = header.getChunkInfo(x, z)
        chunkTag = mclevel.readChunk(x, z, file, header)
    chunk = mclevel.nbtToChunk(chunkTag)
    # generate examples of the chunk
    nbt.tagToJson('json', 'chunk.' + str(x) + '.' + str(z) + '.nbt', chunkTag)
    print('block 0, 70, 0 is id', chunk.getBlock(0, 70, 0).id)
    
def editDemo():
    """Set block 0, 70, 0 to bedrock (id:7)"""
    # make sure we are operating on a clean (noncorrupt) file
    print('# Editing demo #')
    shutil.copy2('nbt/region/r.0.0.mca', 'gen/r.0.0.mca')
    
    vFile = io.BytesIO()
    with open('gen/r.0.0.mca', mode='rb') as file:
        print('Copying file to memory...')
        vFile.write(file.read())
    print('\tCopy successful, copied', len(vFile.getbuffer()), 'bytes')
    
    header = mclevel.RegionHeader(0, 0, vFile)
    chunk = mclevel.nbtToChunk(mclevel.readChunk(0, 0, vFile, header))
    print('block 0, 70, 0 is block id', chunk.getBlock(0, 70, 0).id)
    mclevel.writeChunk(mclevel.chunkToNbt(chunk), vFile, header,
                       safetyMax=5 * 1024 * 1024)

readIntoJSON(0, 0)
editDemo()
# TODO: make it work. write now it corrupts the file...