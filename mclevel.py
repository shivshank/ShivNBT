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
    """ Returns the NBT Tag describing a chunk at offset within the region file
    """
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
    return reader.read()

def parseChunkNbt(root):
    chunkDict = root.pythonify()
    cx, cz = chunkDict['Level']['xPos'], chunkDict['Level']['zPos']
    chunk = Chunk(cx, cz)
    for section in chunkDict['Level']['Sections']:
        blocks = []
        sectionY = section['Y']
        # 8 bits per block
        ids = section['Blocks']
        # 4 bits per block
        try:
            add = section['Add']
        except KeyError:
            add = None
        # 4 bits per block
        data = section['Data']
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

def writeChunk(tag, offset, regionFile):
    # TODO: update chunk header offset/size, right now we just pray!
    b = io.BytesIO()
    writer = nbt.NbtWriter(b)
    writer.write(tag)
    b.seek(0)
    data = b.read()
    # seek to the start of the chunk in the region file
    regionFile.seek(offset * 4096)
    # write the length of this chunks data + 1 for compression type
    regionFile.write((len(data) + 1).to_bytes(3, 'big', signed=True))
    # we are using compression type 2, zlib
    regionFile.write(b'\x02')
    # write the chunk data!
    data = zlib.compress(data)
    regionFile.write(data)

def getChunkNbt(chunk):
    pass

class Chunk:
    def __init__(self, xPos, zPos, inhabitedTime=0):
        self.sections = {}
        self.biomes = []
        self.heightmap = []
        self.inhabitedTime = inhabitedTime
        self.x = xPos
        self.z = zPos
    def addSection(self, y, blocks):
        # blocks are ordered YZX
        self.sections[y] = blocks
    def getBlock(self, x, y, z):
        if x > 15 or x < 0 or y > 255 or y < 0 or z > 15 or z < 0:
            raise ValueError('getBlock takes local chunk block coordinates')
        # blocks are ordered YZX
        try:
            return self.sections[y//16][(y & 15)*256 + z*16 + x]
        except KeyError:
            # the section does not exist
            return None
    def getAsciiYCrossSection(self, y):
        out = []
        for z in range(16):
            out.append([])
            for x in range(16):
                b = self.getBlock(x, y, z)
                b = str(b.id) + ((':' + str(b.data)) if b.data != 0 else '')
                out[z].append(b)
            out[z] = ' | '.join(out[z])
        return '\n'.join(out)

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
    def getChunk(self, x, z):
        """ Chunks are always in global chunk coordinates """
        # convert global coords to internal coords
        x -= self.x * 32
        z -= self.z * 32
        if x < 0 or z < 0 or x > 31 or z > 31:
            raise ValueError('Chunk is not in region ('
                           + str(self.x) + ', ' + str(self.z) + ')')

        try:
            return self.chunks[self._toChunkId(x, z)]
        except KeyError:
            raise ValueError('Chunk has not been generated yet.')
    def _toChunkId(self, x, z):
        return x + z * 32

class MinecraftWorld:
    def __init__(self, savePath):
        self.path = savePath
        self.regionCache = {}
        self.chunkCache = {}
        self.cachedChunks = 0
        self.cachedRegions = 0
    def getBlock(self):
        pass
    def getChunk(self, x, z):
        pass
    def _dropChunk(self):
        pass
    def _dropRegion(self):
        pass

def getRegionPos(chunkX, chunkZ):
    return (chunkX >> 5, chunkZ >> 5)