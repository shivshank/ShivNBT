import sys
import os.path as path
import io
import shutil
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
        chunkTag = mclevel.readChunk(x, z, file, header)
    chunk = mclevel.nbtToChunk(chunkTag)
    nbt.tagToJson('json', 'chunk.' + str(x) + '.' + str(z) + '.nbt', chunkTag)
    print('block 0, 70, 0 is id', chunk.getBlock(0, 70, 0).id)
    
def editDemo():
    """Set block 0, 70, 0 to bedrock (id:7)"""
    print('# Editing demo #')
    
    vFile = io.BytesIO()
    with open('nbt/region/r.0.0.mca', mode='rb') as file:
        print('\tCopying file to memory...')
        vFile.write(file.read())
    print('\tCopy successful, copied', len(vFile.getbuffer()), 'bytes')
    
    header = mclevel.RegionHeader(0, 0, vFile)
    chunk = mclevel.nbtToChunk(mclevel.readChunk(0, 0, vFile, header))
    chunk.lightPopulated = 0
    print('\tblock 0, 70, 0 is block id', chunk.getBlock(0, 70, 0).id)
    print('\tchanging block')
    chunk.setBlock(0, 70, 0, mclevel.Block(7, 0))
    print('\tblock 0, 70, 0 is block id', chunk.getBlock(0, 70, 0).id)
    mclevel.writeChunk(mclevel.chunkToNbt(chunk), vFile, header,
                       safetyMax=5 * 1024 * 1024)
    print('Virtual file is', len(vFile.getbuffer()),
          'bytes. Write to disk (y/n)?')
    if input().startswith('y'):
        with open('gen/r.0.0.mca', mode='wb') as file:
            vFile.seek(0)
            file.write(vFile.read())

def airChunk(x, z):
    print('# Delete Demo #')
    rx, rz = mclevel.getRegionPos(x, z)
    p = 'nbt/region/r.' + str(rx) + '.' + str(rz) + '.mca'

    c = mclevel.Chunk(x, z)
    c.setBlock(7, 0, 7, mclevel.Block(7, 0))
    c.lightPopulated = 0
    with open(path.join('gen', path.basename(p)), mode='r+b') as file:
        header = mclevel.RegionHeader(rx, rz, file)
        mclevel.writeChunk(mclevel.chunkToNbt(c), file, header,
                           safetyMax=5 * 1024 * 1024)

def seekTest():
    with open('nbt/region/r.0.0.mca', mode='rb') as file:
        vFile = io.BytesIO(file.read())

    header = mclevel.RegionHeader(0, 0, vFile)
    offset, size, timestamp = header.getChunkInfo(0, 0)
    pos = header.file.tell()
    header.setChunkInfo(0, 0, offset, size)
    print('old pos:', pos, '\nnew pos:', header.file.tell())

readIntoJSON(0, 0)
editDemo()
airChunk(0, 1)
seekTest()