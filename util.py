def _retainFilePos(fileAttr=None, fileArg=None, fileKwArg=None):
    """ Prevent file/buffer/stream object's position from changing.
        fileAttr - implies that we are wrapping a method and that argument[0]
        of the wrapped function is self/instance and fileObj is self.fileAttr
        fileArg - implies that args[fileArg] will be the fileObj
        fileKwArg - implies that kwargs[fileKwArg] will be the fileObj
    """
    # If this introduces too much overhead accessing the args fileAttr, fileArg,
    # and fileKwArg, this may work better re-written as "class _retainFilePOs"
    # or by storing fileAttr inside the wrapper function's scope...
    # or maybe just simplify and make this only work on the RegionHeader
    # class...
    def wrapper(func):
        def wrapped(*args, **kwargs):
            if fileAttr is not None:
                # args[0] should be the 'self' object
                fileObj = getattr(args[0], fileAttr)
            elif fileKwArg is not None:
                # this should never be an error unless the caller of the wrapped
                # method passes the wrong arguments
                fileObj = kwargs[fileKwArg]
            else:
                fileObj = args[fileArg if fileArg is not None else 0]
            pos = fileObj.tell()
            res = func(*args, **kwargs)
            fileObj.seek(pos)
            return res
        return wrapped
    return wrapper
