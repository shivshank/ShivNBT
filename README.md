Here is my own implementation of the NBT file format, such as the one used in Minecraft. As of writing (March 5, 2016), it appears able to properly parse some of the files (such as level.dat).

TODO:
 * allow writing NBT files
 * to/from JSON converter (with some kind of definition file to explain how numbers are stored)
 * read level/region/chunk files (.mca, etc)