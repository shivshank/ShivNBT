import gzip
import struct
import pprint

def openNbt(path, gzipped=False):
    if gzipped:
        return gzip.open(path, mode='rb')
    else:
        return open(path, mode='rb')

def isGzipped(stream):
    """ -> True if this stream is most likely gzipped
        checks if the stream begins with the gzipped magic numbers
    """
    pos = stream.tell()
    res = stream.read(2) == b'\x1f\x8b'
    stream.seek(pos)
    return res

class Tag:
    TAG_End = 0
    TAG_Byte = 1
    TAG_Short = 2
    TAG_Int = 3
    TAG_Long = 4
    TAG_Float = 5
    TAG_Double = 6
    TAG_Byte_Array = 7
    TAG_String = 8
    TAG_List = 9
    TAG_Compound = 10
    TAG_Int_Array = 11
    
    def __init__(self, id, name, val=None):
        self.id = id
        self.name = name
        self.value = val
    def __str__(self):
        if self.id in (Tag.TAG_Byte_Array, Tag.TAG_Int_Array, Tag.TAG_List):
            return str([str(i) for i in self.value])
        elif self.id == Tag.TAG_Compound:
            return str(dict((k, str(v)) for k, v in self.value.items()))
            
        return str(self.value)
    def pythonify(self):
        if self.id in (Tag.TAG_Byte_Array, Tag.TAG_Int_Array, Tag.TAG_List):
            return self.value
        elif self.id == Tag.TAG_Compound:
            return dict((k, v.pythonify()) for k, v in self.value.items())
            
        return self.value
    def prettyprint(self, indent=2):
        return pprint.pprint(self.pythonify(), indent=indent)

class NbtReader:
    payloads = {
        Tag.TAG_End: None,
        Tag.TAG_Byte: 'readByte',
        Tag.TAG_Short: 'readShort',
        Tag.TAG_Int: 'readInt',
        Tag.TAG_Long: 'readLong',
        Tag.TAG_Float: 'readFloat',
        Tag.TAG_Double: 'readDouble',
        Tag.TAG_Byte_Array: 'readByteArray',
        Tag.TAG_String: 'readString',
        Tag.TAG_List: 'readList',
        Tag.TAG_Compound: 'readCompound',
        Tag.TAG_Int_Array: 'readIntArray'
    }
    
    def __init__(self, stream):
        self.file = stream
        self.root = None
    def parse(self):
        self.root = self.readTag()
        return self.root
    def readTag(self):
        t = self.readTagHeader()
        if t.id == Tag.TAG_End:
            return t
        
        try:
            t.value = self.parsePayload(t.id)
        except KeyError:
            raise NotImplementedError('Encountered unkown tag id:',
                                      t.id, t.name)

        return t
    def readTagHeader(self):
        id = self.readByte()
        if id == 0:
            return Tag(id, '')
        t = Tag(id, self.readString(self.readShort()))
        return t
    def parsePayload(self, id):
        return getattr(self, NbtReader.payloads[id])()
    def readCompound(self):
        result = {}
        while True:
            nxt = self.readTag()
            if nxt.id == 0:
                break
            result[nxt.name] = nxt
        return result
    def readList(self):
        listType = self.readByte()
        listLength = self.readInt()
        value = []
        for i in range(listLength):
            value.append(self.parsePayload(listType))
        return value
    def readByteArray(self):
        size = self.readInt()
        value = []
        for i in range(size):
            value.append(self.parsePayload(Tag.TAG_Byte))
        return value
    def readIntArray(self):
        size = self.readInt()
        value = []
        for i in range(size):
            value.append(self.parsePayload(Tag.TAG_Int))
        return value
    # numeric tags
    def readDouble(self):
        return struct.unpack('>d', self.file.read(8))[0]
    def readFloat(self):
        return struct.unpack('>f', self.file.read(4))[0]
    def readLong(self):
        return int.from_bytes(self.file.read(8), byteorder='big')
    def readInt(self):
        return int.from_bytes(self.file.read(4), byteorder='big')
    def readShort(self):
        return int.from_bytes(self.file.read(2), byteorder='big')
    def readByte(self):
        return int.from_bytes(self.file.read(1), byteorder='big')
    def readString(self, length=None):
        if length is None:
            return self.readString(self.readShort())
        s = self.file.read(length)
        s = s.decode('utf-8')
        return s

if __name__ == "__main__":
    with openNbt('demo/level.dat', gzipped=True) as file:
        NbtReader(file).parse().prettyprint()