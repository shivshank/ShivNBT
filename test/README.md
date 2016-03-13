# Using the test scripts
To use these scripts, you should create three folders in this directory:
 * nbt
 * json
 * gen

The nbt directory is for containing original files from minecraft, such as level.dat(s) and region files. Region files (.mca) should be placed like so: nbt/region/*.mca

The json directory will contain human readable(!) versions of the NBT files if/when the scripts generate them.

Finally, gen will contain any files that should be directly usable by Minecraft! These may be region files, level.dats, etc.