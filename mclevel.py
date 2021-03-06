"""
    Here are some facilities for parsing Minecraft level files.
"""
import os
import os.path
import time
import zlib
import nbt
import io
import math
import json
from util import _retainFilePos
import gzip

class MinecraftLevel:
    """ Responsible for auxillary data about a level, like the level.dat, etc
    """
    def __init__(self, pathToWorld, levelOptions=None):
        self.path = pathToWorld
        # only try making the endmost file since only that represents the level
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        self.levelFile = os.path.join(self.path, "level.dat")
        if "level.dat" not in os.listdir(self.path):
            # load in the default data from the format file
            initialDataFile = 'formats/level.dat.json'
            with open(initialDataFile, mode='r') as file:
                self._levelOptions = json.load(file)
        else:
            # load in the data from the existing file
            with gzip.open(self.levelFile) as file:
                reader = nbt.NbtReader(file)
                self._levelOptions = reader.read().pythonify()
        if levelOptions is not None:
            # merge the requested changes in
            self.levelOptions.update({"Data": levelOptions})
        overworldPath = os.path.join(self.path, 'region')
        netherPath = os.path.join(self.path, 'DIM-1')
        endPath = os.path.join(self.path, 'DIM1')
        if not os.path.exists(overworldPath):
            os.mkdir(overworldPath)
        if not os.path.exists(netherPath):
            os.mkdir(netherPath)
        if not os.path.exists(endPath):
            os.mkdir(endPath)
        self.overworld = MinecraftWorld(overworldPath)
        self.nether = MinecraftWorld(netherPath)
        self.end = MinecraftWorld(endPath)
    @property
    def levelOptions(self):
        # hide the 'Data' tag from observers
        return self._levelOptions['Data']
    @levelOptions.setter
    def levelOptions(self, value):
        self._levelOptions['Data']
    def writeLevelOptions(self):
        levelFile = self.levelFile
        with open('formats/level.tagtypes.json', mode='r') as file:
            tagTypes = json.load(file)
        nbtTag = nbt.fromDict("", self._levelOptions, tagTypes)
        with gzip.open(levelFile, mode='wb') as file:
            writer = nbt.NbtWriter(file)
            writer.write(nbtTag)
    def writeAll(self):
        self.writeLevelOptions()
        self.overworld.writeAll()
        self.nether.writeAll()
        self.end.writeAll()
    def __enter__(self):
        self.overworld = self.overworld.__enter__()
        self.nether = self.nether.__enter__()
        self.end = self.end.__enter__()
        return self
    def __exit__(self, *args):
        # TODO: handle exceptions properly
        self.overworld.__exit__(*args)
        self.nether.__exit__(*args)
        self.end.__exit__(*args)

class MinecraftWorld:
    def __init__(self, regionPath, safetyMax=10*1024*1024*1024):
        self.path = regionPath
        self.regionCache = {}
        self.chunkCache = {}
        self.timestamps = {}
        self.cachedChunks = 0
        self.maxChunks = 32
        self.cachedRegions = 0
        self.maxRegions = 4
        self.handles = []
        # 10 gigabyte default
        self.regionFileMaxSize = safetyMax
    def getBlock(self, x, y, z):
        c = self.getChunk(x//16, z//16)
        x, z = x & 15, z & 15
        return c.getBlock(x, y, z)
    def setBlock(self, x, y, z, b):
        c = self.getChunk(x//16, z//16)
        x, z = x & 15, z & 15
        c.setBlock(x, y, z, b)
        self.timestamps[(x//16, z//16)] = time.time()
    def fillRegion(self, xMin, yMin, zMin, xSize, height, zSize, b):
        xMax = xMin + xSize
        zMax = zMin + zSize
        yMax = yMin + height
        # if this is too slow too often, we could probably optimize this quite a
        # bit by working in groups of chunks!
        for z in range(zMin, zMax):
            for x in range(xMin, xMax):
                for y in range(yMin, yMax):
                    self.setBlock(x, y, z, b)
    def initializeArea(self, xMin, zMin, xSize, zSize, terrainPopulated):
        for z in range(zMin, zMin + zSize):
            for x in range(xMin, xMin + xSize):
                c = self.getChunk(x, z)
                c.terrainPopulated = terrainPopulated
    def getChunk(self, x, z):
        try:
            return self.chunkCache[(x, z)]
        except KeyError:
            # we need to load the chunk
            pass
        header = self.getRegion(*getRegionPos(x, z))
        chunkNbt = readChunk(x, z, header)
        if chunkNbt is None:
            chunk = Chunk(x, z)
        else:
            chunk = nbtToChunk(chunkNbt)

        self.chunkCache[(x, z)] = chunk
        self.timestamps[(x, z)] = time.time()
        # drop a chunk if we have too many in memory
        self.cachedChunks += 1
        if self.cachedChunks > self.maxChunks:
            # drop the last updated chunk
            old = self._getOldestChunk()
            self.writeChunk(*old)
            self._dropChunk(*old)
        return chunk
    def getRegion(self, x, z):
        # REFACTOR: this function might do a little too much
        try:
            return self.regionCache[(x, z)]
        except KeyError:
            # we need to load the region
            pass
        r = os.path.join(self.path, 'r.' + str(x) + '.' + str(z) + '.mca')
        # open the file
        try:
            try:
                # try opening the file for reading and writing, don't truncate
                f = open(r, mode='r+b')
            except FileNotFoundError:
                # w+b will truncate the file, which won't matter if it doesn't
                # exist
                f = open(r, mode='w+b')
                # write an empty header
                f.write(b'\x00'*(4096*2))
        except IOError as e:
            print('something went wrong reading the files')
            raise e
        # create the header object
        header = RegionHeader(x, z, f)
        self.regionCache[(x, z)] = header
        # record that we have the file handle
        self.handles.append(f)
        self.cachedRegions += 1
        if self.cachedRegions > 4:
            # drop the last updated region
            old = self._getOldestRegion()
            self.writeRegion(*old)
            self._dropRegion(*old)
        return header
    def writeChunk(self, x, z):
        c = self.chunkCache[(x, z)]
        rx, rz = getRegionPos(x, z)
        assert self.regionCache[(rx, rz)], "region was not loaded"
        writeChunk(chunkToNbt(c), self.regionCache[(rx, rz)])
    def writeRegion(self, x, z):
        # writes all the chunks in this region
        r = (x, z)
        for c in self.chunkCache.keys():
            if getRegionPos(*c) == r:
                self.writeChunk(*c)
    def writeAll(self):
        # implicitly writes all regions
        for c in self.chunkCache.keys():
            self.writeChunk(*c)
    def clearCache(self):
        """ Deletes all unwritten changes. """
        for i in self.regionCache.keys():
            self._dropRegion(*i)
    def _getOldestChunk(self):
        oldestTime = time.time()
        oldest = None
        for k, v in self.timestamps.items():
            if v < oldestTime:
                oldest = k
        # there may not always be an oldest chunk... ie if everything happens
        # REALLY fast
        if oldest is None:
            oldest = next(iter(self.timestamps.items()))[0]
        return oldest
    def _dropChunk(self, x, z):
        """ Drop a chunk (does not write the chunk) """
        del self.chunkCache[(x, z)]
        del self.timestamps[(x, z)]
        self.cachedChunks -= 1
    def _dropRegion(self, x, z):
        """ Drop a region and all chunks in it (does not write the chunks) """
        # drop all the chunks in this region
        chunks = self._getCachedInRegion(self, x, z)
        for c in chunks:
            self._dropChunk(*c)
        # delete the region, close the file
        r = self.regionCache[(x, z)]
        r.file.close()
        self.handles.remove(r.file)
        del self.regionCache[(x, z)]
        self.cachedRegions -= 1
    def _getCachedInRegion(self, x, z):
        out = []
        for k, v in self.chunkCache.items():
            if getRegionPos(*k) == (x, z):
                out.append(k)
        return out
    def getRegionTimestamp(self, x, z):
        """ A region is as old as it's newest chunk! """
        # When in doubt assume it's '70
        t = 0
        for k, v in self.chunkCache.items():
            if getRegionPos(*k) == (x, z):
                t = max(self.timestamps[k], t)
        return t
    def __exit__(self, exctype, exc, trace):
        try:
            self.closeAll()
        except Exception as e:
            # todo: handle closing exceptions...
            raise e
        if exc is not None:
            raise exc
    def __enter__(self):
        return self
    def closeAll(self):
        for i in self.handles:
                i.close()
    def __repr__(self):
        attrs = {
            'cachedChunks': self.cachedChunks,
            'cachedRegions': self.cachedRegions,
            'regions': self.regionCache.keys()
        }
        return 'MinecraftWorld' + str(attrs)

def readChunk(x, z, regionHeader):
    """ Returns the NBT Tag describing a chunk at offset within the region file.
        If the chunk does not exist, returns None.
    """
    stream = regionHeader.file
    offset, size, timestamp = regionHeader.getChunkInfo(x, z)
    if offset is None:
        return None

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

def writeChunk(tag, regionHeader, safetyMax=None):
    regionFile = regionHeader.file
    x, z = tag['Level']['xPos'].value, tag['Level']['zPos'].value
    offset, size, timestamp = regionHeader.getChunkInfo(x, z)
    writer = nbt.NbtWriter(io.BytesIO(), safetyMax=safetyMax)
    writer.write(tag)
    writer.file.seek(0)
    data = writer.file.read()
    zipped = zlib.compress(data)
    newsize = math.ceil((len(zipped) + 4 + 1)/4096)
    if newsize != size:
        print('writeChunk: Chunk resize occured')
        regionHeader.resize(x, z, newsize)
    # re-obtain the offset in case it has changed
    offset, size, timestamp = regionHeader.getChunkInfo(x, z)
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
    if chunk.biomes is not None:
        print('Writing biomes...')
        print(chunk.biomes)
        root.value["Biomes"] = nbt.Tag("TAG_Byte_Array", "Biomes", chunk.biomes)

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
    def fillBiome(self, biomeId):
        self.biomes = [biomeId for i in range(256)]
    def setBiome(self, x, z, biomeId, defaultBiome=-1):
        if self.biomes is None:
            self.fillBiome(defaultBiome)
        self.biomes[z*16 + x] = biomeId

class Block:
    def __init__(self, id, data):
        self.id = id
        self.data = data

class RegionHeader:
    """ Wraps a .mca Anvil world file.
        Reads and writes directly from the buffer/stream/file.

        It is the caller's responsibility to manage the file.

        User could also pass an in memory buffer.
    """
    def __init__(self, regionX, regionZ, stream):
        self.file = stream
        if self.file.read(1) == b'':
            # write the two initial sectors if the file is empty
            self.file.seek(0)
            self.file.write(b'\x00'*4096*2)
        self.x = regionX
        self.z = regionZ
    @_retainFilePos(fileAttr='file')
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

        if location == 0 and size == 0:
            return None, None, None

        self.file.seek(pos + 4096)
        timestamp = int.from_bytes(self.file.read(4), 'big', signed=False)
        return location, size, timestamp
    def _toChunkId(self, x, z):
        return x + z * 32
    @_retainFilePos(fileAttr='file')
    def countChunks(self):
        self.file.seek(0)
        c = 0
        for i in range(1024):
            if self.file.read(4) != b'\x00\x00\x00\x00':
                c += 1
        return c
    @_retainFilePos(fileAttr='file')
    def countSectors(self):
        self.file.seek(0)
        s = 0
        for i in range(1024):
            nxt = self.file.read(4)
            if nxt != b'\x00\x00\x00\x00':
                s += nxt[-1]
        return s
    @_retainFilePos(fileAttr='file')
    def markUpdate(self, x, z):
        # recall: timestamp is 4096 bytes ahead of offset position
        pos = self._getIndex(x, z) + 4096
        self.file.seek(pos)
        self.file.write( int(time.time()).to_bytes(4, 'big', signed=False) )
    @_retainFilePos(fileAttr='file')
    def resize(self, x, z, newSize):
        offset, size, timestamp = self.getChunkInfo(x, z)
        # the chunks exists and the chunk shrank
        if offset is not None and newSize < size:
            self.setChunkInfo(x, z, offset, newSize)
            # if we shrunk, zero out the old space
            dif = newSize - size
            self.file.seek(4096 * (offset + newSize))
            self.file.write(b'\x00'*(dif*4096))
            return
        # if the chunk doesn't exist:
        elif offset is None:
            newOffset = self._alloc(newSize)
            self.setChunkInfo(x, z, newOffset, newSize)
            # make sure the file gets padded to the right size
            self.file.seek(newOffset * 4096)
            self.file.write(b'\x00'*(newSize*4096))
            return
        # the chunk grew... this could get ugly!
        # make it look like this chunk's space is not taken
        # (_isFree will otherwise tell us that it is taken)
        self.setChunkInfo(x, z, 0, 0)
        # do we need to change the offset or can we just expand it?
        if self._isFree(*range(offset, offset+newSize)):
            self.setChunkInfo(x, z, offset, newSize)
            return
        # we must reallocate this chunk...
        newOffset = self._alloc(newSize)
        self.setChunkInfo(x, z, newOffset, newSize)
        # grab the old data and set it to zero if it exists
        # (setting it to zero is probably unnecessary)
        self.file.seek(offset * 4096)
        data = self.file.read(size*4096)
        self.file.seek(offset * 4096)
        self.file.write(b'\x00'*(size*4096))
        self.file.seek(newOffset * 4096)
        self.file.write(data)
    @_retainFilePos(fileAttr='file')
    def setChunkInfo(self, x, z, newOffset, newSize):
        pos = self._getIndex(x, z)
        self.file.seek(pos)
        self.file.write( newOffset.to_bytes(3, 'big', signed=True) )
        self.file.write( newSize.to_bytes(1, 'big', signed=True) )
    @_retainFilePos(fileAttr='file')
    def _alloc(self, size):
        self.file.seek(0, 2)
        pos = self.file.tell()//4096
        assert self.file.tell() & 4095 == 0
        return pos
    def _getIndex(self, x, z):
        return 4 * ((x & 31) + (z & 31) * 32)
    @_retainFilePos(fileAttr='file')
    def _isFree(self, *sectors):
        """ Brute force check if each sector in sectors is free """
        if 0 in sectors or 1 in sectors:
            raise ValueError("Sectors 0 and 1 are reserved for the header")
        self.file.seek(0)
        for i in range(1024):
            location = int.from_bytes(self.file.read(3), 'big', signed=False)
            size = int.from_bytes(self.file.read(1), 'big', signed=False)
            for j in range(location, location+size):
                if j in sectors:
                    return False
        return True
    @_retainFilePos(fileAttr='file')
    def _pack(self):
        """ Squashes the file size down, packing the chunks tightly together.
        """
        pass
    @_retainFilePos(fileAttr='file')
    def findHoles(self):
        """ Here's a fun analysis method! Finds the "holes" in the file. """
        self.file.seek(0, 2)
        fileSize = self.file.tell()
        # all files should be 4096 byte-aligned
        assert math.floor(fileSize/4096) == fileSize//4096
        fileSize //= 4096
        # it's probably faster to remove indices from a set
        holes = set(i for i in range(2, fileSize))
        self.file.seek(0)
        for i in range(1024):
            location = int.from_bytes(self.file.read(3), 'big', signed=False)
            size = int.from_bytes(self.file.read(1), 'big', signed=False)
            for j in range(location, location+size):
                holes.remove(j)
        return holes

def getRegionPos(chunkX, chunkZ):
    return (chunkX >> 5, chunkZ >> 5)
