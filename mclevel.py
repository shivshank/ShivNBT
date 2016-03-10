""" 
    Here are some facilities for parsing Minecraft level files.
"""
import os.path
import time
import zlib
import nbt
import io
import math

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
        
def readChunk(x, z, stream, regionHeader):
    """ Returns the NBT Tag describing a chunk at offset within the region file
    """
    offset, size, timestamp = regionHeader.getChunkInfo(x, z)
    # offset and size are in terms of 4096kib
    stream.seek(offset * 4096, 0)
    # the length in bytes of the remaining chunk data
    # (note that all the chunks are padded to be 4096 byte aligned)
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

def writeChunk(tag, regionFile, regionHeader, safetyMax=None):
    x, z = tag['Level']['xPos'].value, tag['Level']['zPos'].value
    offset, size, timestamp = regionHeader.getChunkInfo(x, z)
    writer = nbt.NbtWriter(io.BytesIO(), safetyMax=safetyMax)
    writer.write(tag)
    writer.file.seek(0)
    data = writer.file.read()
    zipped = zlib.compress(data)
    newsize = math.ceil((len(zipped) + 4 + 1)/4096)
    if newsize > size:
        print('writeChunk: Chunk size increase occured')
        # we gained at least one second, so transpose all the chunks in the file
        regionHeader.resize(x, z, newsize)
    # seek to the start of the chunk in the region file
    regionFile.seek(offset * 4096, 0)
    # write the length of this chunks data, + 1 for compression type
    regionFile.write((len(zipped) + 1).to_bytes(4, 'big', signed=False))
    # we are using compression type 2, zlib
    regionFile.write(b'\x02')
    # write the chunk data!
    regionFile.write(zipped)
    # pad to multiple of 4096 bytes
    remaining = 4096 - (regionFile.tell() & 4095)
    # both of these should be valid ways to compute the required padding
    assert remaining == 4096 * newsize - len(zipped) - 5
    regionFile.write(b'\x00'*remaining)
    # make sure we end in the right place
    assert regionFile.tell() & 4095 == 0
    # mark the current time on the chunk
    regionHeader.markUpdate(x, z)

def nbtToChunk(root):
    """ Create a chunk from an NBT tag. """
    chunkDict = root.pythonify()['Level']
    cx, cz = chunkDict['xPos'], chunkDict['zPos']
    
    # initialize the chunk object
    chunk = Chunk(cx, cz,
                  terrainPopulated=chunkDict['TerrainPopulated'],
                  inhabitedTime=chunkDict['InhabitedTime'],
                  lightPopulated=chunkDict['LightPopulated'],
                  lastUpdate=chunkDict['LastUpdate'])
    
    for section in chunkDict['Sections']:
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
                        id += (add[index//2] & halfbyte) << 8
                    blockData = data[index//2] & halfbyte
                    block = Block(id, blockData)
                    blocks.append(block)
                    index += 1
        chunk.addSection(sectionY, blocks)

    return chunk

def chunkToNbt(chunk):
    root = nbt.Tag('TAG_Compound', '', [
        nbt.Tag("TAG_Int", "DataVersion", 169),
        nbt.Tag("TAG_Compound", "Level", [
            nbt.Tag("TAG_Int", "xPos", chunk.x),
            nbt.Tag("TAG_Int", "zPos", chunk.z),
            nbt.Tag("TAG_Long", "LastUpdate", chunk.lastUpdate),
            nbt.Tag("TAG_Byte", "LightPopulated", chunk.lightPopulated),
            nbt.Tag("TAG_Byte", "TerrainPopulated", chunk.terrainPopulated),
            nbt.Tag("TAG_Byte", "V", 1),
            nbt.Tag("TAG_Long", "InhabitedTime", chunk.inhabitedTime),
            nbt.Tag("TAG_Int_Array", "HeightMap", chunk.genHeightmap()),
            nbt.Tag("TAG_List", "Sections", [], nbt.Tag.TAG_Compound),
            nbt.Tag("TAG_List", "Entities", [], nbt.Tag.TAG_End),
            nbt.Tag("TAG_List", "TileEntities", [], nbt.Tag.TAG_End)
        ])
    ])
    # Things that may or may not exist:
    # Biomes, TileTicks
    sects = len(chunk.sections.keys())
    if sects == 0:
        root['Level']['Sections'].listType = nbt.Tag.TAG_End
    else:
        for k, v in chunk.sections.items():
            root['Level']['Sections'].value.append(_sectionToNbt(k, v))

    return root

def _sectionToNbt(y, section):
    # the root is the payload of a compound tag, which is a dict
    root = dict((i.name, i) for i in [
        nbt.Tag("TAG_Byte", "Y", y),
        nbt.Tag("TAG_Byte_Array", "Blocks", []),
        nbt.Tag("TAG_Byte_Array", "Add", [0 for i in range(2048)]),
        nbt.Tag("TAG_Byte_Array", "Data", [0 for i in range(2048)]),
        nbt.Tag("TAG_Byte_Array", "SkyLight", [0 for i in range(2048)]),
        nbt.Tag("TAG_Byte_Array", "BlockLight", [0 for i in range(2048)])
    ])
    blocks = root["Blocks"].value
    add = root["Add"].value
    data = root["Data"].value
    index = 0
    for y in range(16):
        for z in range(16):
            for x in range(16):
                # even blocks use the second half of the halfbytes
                halfbyteShift = 4 if index & 1 else 0
                b = section[index]
                blocks.append(b.id & 0xFF)
                add[index//2] = add[index//2] & ((b.id >> 8) << halfbyteShift)
                data[index//2] = data[index//2] & ((b.data & 0x0F) << halfbyteShift)
                index += 1
    if sum(add) == 0:
        del root['Add']

    return root

class Chunk:
    def __init__(self, xPos, zPos, **kw):
        """ Create an empty chunk. """
        self.sections = {}
        self.topSection = 0
        self.biomes = None
        self.heightmap = None
        self.x = xPos
        self.z = zPos
        
        self.inhabitedTime = kw.get('inhabitedTime', 0)
        self.terrainPopulated = kw.get('terrainPopulated', 1)
        self.lightPopulated = kw.get('lightPopulated', 0)
        self.lastUpdate = kw.get('lastUpdate', 0)
    def addSection(self, sectionY, blocks):
        # blocks are ordered YZX
        self.sections[sectionY] = blocks
        self.topSection = max(self.topSection, sectionY)
    def getBlock(self, x, y, z):
        if x > 15 or x < 0 or y > 255 or y < 0 or z > 15 or z < 0:
            raise ValueError('getBlock takes local chunk block coordinates')
        # blocks are ordered YZX
        try:
            return self.sections[y//16][(y & 15)*256 + z*16 + x]
        except KeyError:
            # the section does not exist
            return None
    def setBlock(self, x, y, z, b):
        index = (y & 15)*256 + z*16 + x
        section = self.sections.get(y//16, None)
        if section is None:
            self._initializeSection(y//16)
        self.sections[y//16][index] = b
    def _initializeSection(self, y):
        arr = []
        for i in range(4096):
            arr.append(Block(0, 0))
        self.sections[y] = arr
        self.topSection = max(self.topSection, y)
    def getAsciiYCrossSection(self, y):
        """ A marginally useful debugging/novelty method. :)"""
        out = []
        for z in range(16):
            out.append([])
            for x in range(16):
                b = self.getBlock(x, y, z)
                b = str(b.id) + ((':' + str(b.data)) if b.data != 0 else '')
                out[z].append(b)
            out[z] = ' | '.join(out[z])
        return '\n'.join(out)
    def genHeightmap(self):
        self.heightmap = [0 for i in range(256)]
        for z in range(16):
            for x in range(16):
                for y in range(255, -1, -1):
                    b = self.getBlock(x, y, z)
                    if b is not None and b.id != 0:
                        self.heightmap[z*16 + x] = y
                        break
        return self.heightmap

class Block:
    def __init__(self, id, data):
        self.id = id
        self.data = data

# here is a decorator for the RegionHeader class
# there's probably a better way to write and store this,
# but I don't know too much about decorators/convention
def _retainFilePos(func):
    def f(*args, **kwargs):
        # args[0] should be the 'self' object
        pos = args[0].file.tell()
        res = func(*args, **kwargs)
        args[0].file.seek(pos)
    return f

class RegionHeader:
    """ Wraps a .mca Anvil world file.
        Reads and writes directly from the buffer/stream/file.
    """
    def __init__(self, regionX, regionZ, stream):
        self.file = stream
        self.x = regionX
        self.z = regionZ
    def getChunkInfo(self, x, z):
        """ Chunks are always in global chunk coordinates """
        # convert global coords to internal coords
        x -= self.x * 32
        z -= self.z * 32
        if x < 0 or z < 0 or x > 31 or z > 31:
            raise ValueError('Chunk is not in region ('
                           + str(self.x) + ', ' + str(self.z) + ')')

        pos = self._getIndex(x, z)
        self.file.seek(pos)
        # I don't think it makes sense for any of these values to be signed
        location = int.from_bytes(self.file.read(3), 'big', signed=False)
        size = int.from_bytes(self.file.read(1), 'big', signed=False)
        self.file.seek(pos + 4096)
        timestamp = int.from_bytes(self.file.read(4), 'big', signed=False)
        return location, size, timestamp
    def _toChunkId(self, x, z):
        return x + z * 32
    def countChunks(self):
        self.file.seek(0)
        c = 0
        for i in range(1024):
            if self.file.read(4) != b'\x00\x00\x00\x00':
                c += 1
        return c
    def markUpdate(self, x, z):
        # recall: timestamp is 4096 bytes ahead of offset position
        pos = self._getIndex(x, z) + 4096
        self.file.seek(pos)
        self.file.write( int(time.time()).to_bytes(4, 'big', signed=False) )
    def resize(self, x, z, newsize):
        raise UnsupportedOperationException("Resizing chunks is not done yet.")
        offset, size, timestamp = self.getChunkInfo(x, z)
        # update this chunks header
        
        # now check every other chunk in the header and offset its location
        # if it occurs ahead of this chunk
    @_retainFilePos
    def setChunkInfo(self, x, z, newOffset, newSize):
        pos = self._getIndex(x, z)
        self.file.seek(pos)
        self.file.write( newOffset.to_bytes(3, 'big', signed=True) )
        self.file.write( newSize.to_bytes(1, 'big', signed=True) )
    @_retainFilePos
    def _alloc(self, size):
        return self.file.seek(0, 2)
    def _getIndex(self, x, z):
        return 4 * ((x & 31) + (z & 31) * 32)
    def _pack(self):
        """ Squashes the file size down, packing the chunks tightly together.
        """
        pass

def getRegionPos(chunkX, chunkZ):
    return (chunkX >> 5, chunkZ >> 5)
