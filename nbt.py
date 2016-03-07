import gzip
import struct
import json
import os.path

def toJson(fileName, outputDir, gzipped=True):
    """ Write an NBT as two JSON files.
        the .tagtypes.json file describes the NBT types of all the tags,
        while the .json file contains the actual values.
        
        Two files are required because JSON (Javascript) only supports a single
        Number type (IEEE floats), so all bytes, shorts, ints, etc are converted
        to floats.
        
        Doubles/longs may be truncated (I presume).
    """
    path, name = os.path.split(fileName)
    tagtypes = os.path.join(outputDir,
                            os.path.splitext(name)[0] + '.tagtypes.json')
    tags = os.path.join(outputDir, name + '.json')
    with gzip.open(fileName) as file:
        root = NbtReader(file).read()
    with open(tagtypes, mode='w') as file:
        json.dump(root.getFormatDict(), file, indent=4)
    with open(tags, mode='w') as file:
        json.dump(root.pythonify(), file, indent=4)

def fromJson(rootName, dataFileName, tagtypesFileName):
    """ Given tagtypes and nbt JSON files, create an NBT Tag. """
    # perhaps we could use the parse_float and parse_int options of the
    # json.load function?
    with open(dataFileName) as file:
        values = json.load(file)
    with open(tagtypesFileName) as tagtypesFile:
        tagtypes = json.load(tagtypesFile)

    return fromDict(rootName, values, tagtypes)

def tagToJson(outputDir, fileName, root):
    """ Given an NBT tag root, write it to outputDir as JSON. """
    # remove whatever directory is attached
    name = os.path.basename(fileName)
    tagtypes = os.path.join(outputDir,
                            os.path.splitext(name)[0] + '.tagtypes.json')
    tags = os.path.join(outputDir, name + '.json')
    with open(tagtypes, mode='w') as file:
        json.dump(root.getFormatDict(), file, indent=4)
    with open(tags, mode='w') as file:
        json.dump(root.pythonify(), file, indent=4)

def fromDict(name, values, types):
    t = Tag(0, name)
    if type(values) == dict:
        # compound tag
        t.id = Tag.TAG_Compound
        t.value = {}
        for k, v in values.items():
            t.value[k] = fromDict(k, v, types[k])
    elif type(values) == list and type(types) == str:
        # int array or byte array
        t.id = getattr(Tag, types)
        t.value = list(values)
    elif type(values) == list and type(types) == list:
        # list tag
        t.id = Tag.TAG_List
        if type(types[0]) == dict:
            # OR they will be a list of compound tags
            t.listType = Tag.TAG_Compound
            t.value = []
            for v, cmpType in zip(values, types):
                compound = {}
                # where v is each dict
                # n.b., v and cmpType should have the same keys
                for name, tag in v.items():
                    compound[name] = fromDict(name, tag, cmpType[name])
                t.value.append(compound)
        else:
            # list tags are denoted in json by [ "TAG_x" ]
            t.listType = getattr(Tag, types[0])
            t.value = list(values)
    elif type(values) == str:
        # string tag
        t.id = Tag.TAG_String
        t.value = values
    else:
        # it's a float or an int
        t.id = getattr(Tag, types)
        t.value = values
    return t

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
    fromId = {
        TAG_End: 'TAG_End',
        TAG_Byte: 'TAG_Byte',
        TAG_Short: 'TAG_Short',
        TAG_Int: 'TAG_Int',
        TAG_Long: 'TAG_Long',
        TAG_Float: 'TAG_Float',
        TAG_Double: 'TAG_Double',
        TAG_Byte_Array: 'TAG_Byte_Array',
        TAG_String: 'TAG_String',
        TAG_List: 'TAG_List',
        TAG_Compound: 'TAG_Compound',
        TAG_Int_Array: 'TAG_Int_Array'
    }
    
    def __init__(self, id, name, val=None, listType=None):
        if type(id) is str:
            id = getattr(Tag, id)
        self.id = id
        self.name = name
        self.value = self.handleInitialValue(val)
        self.listType = listType
    def handleInitialValue(self, val):
        """ Convenience method for creating tags programmatically.
            If this is a compound tag and val is a list, val will be converted
            into a dict.
        """
        if self.id != Tag.TAG_Compound or type(val) is not list:
            return val

        return dict((i.name, i) for i in val)
    def pythonify(self):
        if self.id == Tag.TAG_List:
            return self._pythonifyPayload(self.value)
        elif self.id == Tag.TAG_Compound:
            return dict((k, v.pythonify()) for k, v in self.value.items())
            
        return self.value
    def prettystr(self, indent=4):
        # JSON dumps looks nice in my opinion than pprint output
        return json.dumps(self.pythonify(), indent=indent)
    def getFormatDict(self):
        if self.id == Tag.TAG_List and self.listType != Tag.TAG_Compound:
            return [Tag.fromId[self.listType]]
        elif self.id == Tag.TAG_List:
            # list type must be TAG_Compound
            out = []
            for i in self.value:
                d = dict((k, v.getFormatDict()) for k, v in i.items())
                out.append(d)
            return out
        elif self.id == Tag.TAG_Compound:
            return dict((k, v.getFormatDict()) for k, v in self.value.items())
        return Tag.fromId[self.id]
    def _pythonifyPayload(self, payload):
        """ TAG_List.value may contain python dict/lists which may contain tags.
            This function will recursively probe deeper until all tags
            are pythonify'd.
        """
        if type(payload) == dict:
            return self._pythonifyDict(payload)
        return self._pythonifyList(payload)
    def _pythonifyDict(self, payload):
        out = {}
        for k, v in payload.items():
            if type(v) == dict:
                out[k] = self._pythonifyPayload(v)
            elif type(v) == list:
                out[k] = self._pythonifyPayload(v)
            elif type(v) == Tag:
                out[k] = v.pythonify()
            else:
                out[k] = i
        return out
    def _pythonifyList(self, payload):
        out = []
        for i in payload:
            if type(i) == dict:
                out.append(self._pythonifyPayload(i))
            elif type(i) == list:
                out.append(self._pythonifyPayload(i))
            elif type(i) == Tag:
                out.append(tag.pythonify())
            else:
                out.append(i)
        return out
    def __getitem__(self, key):
        return self.value[key]

class NbtWriter:
    payloads = {
        Tag.TAG_End: None,
        Tag.TAG_Byte: 'writeByte',
        Tag.TAG_Short: 'writeShort',
        Tag.TAG_Int: 'writeInt',
        Tag.TAG_Long: 'writeLong',
        Tag.TAG_Float: 'writeFloat',
        Tag.TAG_Double: 'writeDouble',
        Tag.TAG_Byte_Array: 'writeByteArray',
        Tag.TAG_String: 'writeString',
        Tag.TAG_List: 'writeList',
        Tag.TAG_Compound: 'writeCompound',
        Tag.TAG_Int_Array: 'writeIntArray'
    }
    
    def __init__(self, stream):
        self.file = stream
    def write(self, tag):
        self.writeHeader(tag)
        self.writePayload(tag.id, tag.value, tag)
    def writeHeader(self, tag):
        self.writeByte(tag.id)
        self.writeString(tag.name)
    def writePayload(self, id, value, tag=None):
        # use the class variable payloads to select a method
        getattr(self, NbtWriter.payloads[id])(payload=value, tag=tag)
    # complex types
    def writeByteArray(self, tag=None, **kw):
        self.writeInt(len(tag.value))
        for i in tag.value:
            self.writeByte(i)
    def writeIntArray(self, tag=None, **kw):
        self.writeInt(len(tag.value))
        for i in tag.value:
            self.writeInt(i)
    def writeList(self, tag=None, **kw):
        self.writeByte(tag.listType)
        self.writeInt(len(tag.value))
        for i in tag.value:
            # if list contains lists, then the second tag argument
            # will be used; if list contains compounds, then the payload
            # argument will be used. This is hacky but it works...
            self.writePayload(tag.listType, i, i)
    def writeCompound(self, payload=None, **kw):
        for t in payload.values():
            self.write(t)
        # write the end tag
        self.writeByte(0)
    # numeric types
    def writeByte(self, payload=None, **kw):
        self.file.write( payload.to_bytes(1, 'big', signed=True) )
    def writeShort(self, payload=None, **kw):
        self.file.write( payload.to_bytes(2, 'big', signed=True) )
    def writeInt(self, payload=None, **kw):
        self.file.write( payload.to_bytes(4, 'big', signed=True) )
    def writeLong(self, payload=None, **kw):
        self.file.write( payload.to_bytes(8, 'big', signed=True) )
    def writeFloat(self, payload=None, **kw):
        self.file.write( struct.pack('>f', payload) )
    def writeDouble(self, payload=None, **kw):
        self.file.write( struct.pack('>d', payload) )
    def writeString(self, payload=None, **kw):
        # all nbt string lengths are defined by a short, not null terminator
        self.writeShort(len(payload))
        self.file.write( payload.encode('utf-8') )

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
    def read(self):
        self.root = self.readTag()
        return self.root
    def readTag(self):
        t = self.readTagHeader()
        if t.id == Tag.TAG_End:
            return t
        
        if t.id == Tag.TAG_List:
            t.listType, t.value = self.parsePayload(t.id)
        else:
            t.value = self.parsePayload(t.id)

        return t
    def readTagHeader(self):
        id = self.readByte()
        if id == 0:
            return Tag(id, '')
        t = Tag(id, self.readString(self.readShort()))
        return t
    def parsePayload(self, id):
        """ -> python value of payload or (list type, value of payload)"""
        try:
            return getattr(self, NbtReader.payloads[id])()
        except KeyError:
            # .payloads[...] will throw the error, not getattr
            raise NotImplementedError('Encountered unkown tag id: ' + id)
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
        return listType, value
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
        return int.from_bytes(self.file.read(8), 'big', signed=True)
    def readInt(self):
        return int.from_bytes(self.file.read(4), 'big', signed=True)
    def readShort(self):
        return int.from_bytes(self.file.read(2), 'big', signed=True)
    def readByte(self):
        return int.from_bytes(self.file.read(1), 'big', signed=True)
    def readString(self, length=None):
        if length is None:
            return self.readString(self.readShort())
        s = self.file.read(length)
        s = s.decode('utf-8')
        return s
    