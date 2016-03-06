""" 
    Here are some facilities for parsing Minecraft level files.

    Minecraft (as release 1.9, 16/03/05) uses region files to specify the level.

    The region file consists of a header (the Region file format) and Chunk
    data, which is in the Anvil file format.

    Each region file consists of an 8kib header (aka the region file). The first
    4096 bytes are location information and the second 4096 bytes are
    timestamps.
"""
import os.path
import time
import zlib
import nbt
import io

def openMca(path):
    # TOOD... this should return some kinda object?
    dir, fileName = os.path.split(path)
    r, x, z, ext = fileName.split('.')
    with open(path, mode='rb') as file:
        chunks = readRegionHeader(int(x), int(z), file)
    return chunks

def readRegionHeader(regionX, regionZ, stream):
    # stream offset = 4 * ((x & 31) + (z & 31) * 32)
    # this implies that every 32 bytes increments the z coordinate
    # timestamp is at location (above formula) + 4096
    x = 0
    z = 0
    header = RegionHeader(regionX, regionZ)
    for chunkId in range(1024):
        pos = stream.tell()
        stream.seek(pos + 4096, 0)
        timestamp = int.from_bytes(stream.read(4), 'big')
        stream.seek(pos, 0)
        offset = int.from_bytes(stream.read(3), 'big')
        size = int.from_bytes(stream.read(1), 'big')
        # the chunk doesn't exist when both of these values are zero
        if offset != 0 or size != 0:
            header.addChunk(x, z, offset, size, timestamp)
        x += 1
        if x == 32:
            x = 0
            z += 1
    return header

def readChunk(offset, size, stream):
    # offset and size are in terms of 4096kib
    stream.seek(offset * 4096, 0)
    # the length in bytes of the chunk
    # (note that all the chunks are 4096byte aligned)
    length = int.from_bytes(stream.read(4), 'big')
    compressionType = int.from_bytes(stream.read(1), 'big')
    if compressionType == 2:
        # zlib decompress the data
        unzipped = io.BytesIO(zlib.decompress(stream.read(length - 1)))
    else:
        # gzip decompress (this is UNTESTED and also not used by minecraft)
        print('Woah... just used gzip to decompress chunk data')
        unzipped = io.BytesIO(gzip.decompress(stream.read(length - 1)))

    reader = nbt.NbtReader(unzipped)
    root = reader.parse()
    
    chunkDict = root.pythonify()
    cx, cz = chunkDict['Level']['xPos'], chunkDict['Level']['zPos']
    chunk = Chunk(cx, cz)
    for section in chunkDict['Level']['Sections']:
        blocks = []
        sectionY = section['Y'].pythonify()
        # 8 bits per block
        ids = section['Blocks'].pythonify()
        # 4 bits per block
        try:
            add = section['Add'].pythonify()
        except KeyError:
            add = None
        # 4 bits per block
        data = section['Data'].pythonify()
        index = 0
        # blocks are stored YZX
        for y in range(16):
            for z in range(16):
                for x in range(16):
                    # bitwise and this with data/add to get the value
                    halfbyte = 0xF0 if index & 1 else 0x0F
                    id = ids[index]
                    # the add tag extends the range of ids
                    if add is not None:
                        id += add[index//2] & (halfbyte << 8)
                    blockData = data[index//2] & halfbyte
                    block = Block(id, blockData)
                    blocks.append(block)
                    index += 1
        chunk.addSection(sectionY, blocks)

    return chunk

class Chunk:
    def __init__(self, xPos, zPos):
        self.sections = {}
        self.x = xPos
        self.z = zPos
    def addSection(self, y, blocks):
        # blocks are ordered YZX
        self.sections[y] = blocks
    def getBlock(self, x, y, z):
        # blocks are ordered YZX
        try:
            return self.sections[y//16][(y & 15)*256 + z*16 + x]
        except KeyError:
            # the section does not exist
            return None

class Block:
    def __init__(self, id, data):
        self.id = id
        self.data = data

class RegionHeader:
    """ Caches which chunks are generated in this region.
        Also stores information on how to locate a chunk in the region file and
        how to find it in the region file.
    """
    def __init__(self, regionX, regionZ):
        self.chunks = {}
        self.count = 0
        self.x = regionX
        self.z = regionZ
    def addChunk(self, localX, localZ, offset, size, epochTimestamp):
        timestamp = time.localtime(epochTimestamp)
        self.chunks[self._toChunkId(localX, localZ)] = (offset, size, timestamp)
        self.count += 1
    def getChunk(self, x, z, isGlobalCoordinate=False):
        if isGlobalCoordinate:
            x -= self.x * 32
            z -= self.z * 32
        return self.chunks[self._toChunkId(x, z)]
    def _toChunkId(self, x, z):
        return x + z * 32

def getRegionPos(chunkX, chunkZ):
    return (chunkX >> 5, chunkZ >> 5)

if __name__ == '__main__':
    with open('demo/r.0.0.mca', mode='rb') as file:
        header = readRegionHeader(0, 0, file)
        offset, size, timestamp = header.getChunk(0, 0)
        chunk = readChunk(offset, size, file)
    print(chunk.getBlock(0, 63, 0).id)