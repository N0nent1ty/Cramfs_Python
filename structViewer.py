from bitstring import ConstBitStream
import stat
import logging
import os
import zlib
import shutil #for delete folder


'''
struct cramfs_super {
	u32 magic;			/* 0x28cd3d45 - random number */
	u32 size;			/* length in bytes */
	u32 flags;			/* feature flags */
	u32 future;			/* reserved for future use */
	u8 signature[16];		/* "Compressed ROMFS" */
	struct cramfs_info fsid;	/* unique filesystem info */
	u8 name[16];			/* user-defined name */
	struct cramfs_inode root;	/* root inode data */
};
'''
class Cramfs_class:
    def __init__(self, input_filename, extract_dir="./output_dir"):
        #create bitstring buffer
        self.cramfs_bitstream_buffer=ConstBitStream(filename=input_filename)
        #configs variable
        self.extract_dir=extract_dir
        self.PAGE_SIZE=4096
        self.ROMBUFFER_BITS=13
        self.ROMBUFFER_SIZE=1<<self.ROMBUFFER_BITS
        self.ROMBUFFERMASK=self.ROMBUFFER_SIZE-1

        #"{0:b}".format(self.CRAMFS_BLK_FLAG_UNCOMPRESSED)=0b10000000000000000000000000000000
        self.CRAMFS_BLK_FLAG_UNCOMPRESSED=1<<31
        #"{0.b}".format(self.CRAMFS_BLK_FLAG_DIRECT_PRT)=0b1000000000000000000000000000000
        self.CRAMFS_BLK_FLAG_DIRECT_PTR=1<<30
        self.CRAMFS_BLK_FLAGS=self.CRAMFS_BLK_FLAG_UNCOMPRESSED | self.CRAMFS_BLK_FLAG_DIRECT_PTR 


        #the accessiable value of this class.
        self.magic=None
        self.size=None
        self.flags=None
        self.future=None
        self.signature=None
        self.cramfs_info=None
        self.name=None
        self.root_Inode=None
        self.start_data = 0xffffffff	# unsigned long startdata=~0ul; start of the data (256 MB = max) */
        self.end_data=0
        self.decompressed_data=None #bytes
        self.read_buffer_block=0
        self.read_buffer=None

        # if the extract directory existied, remove it first
        if os.path.exists(self.extract_dir):
            shutil.rmtree(self.extract_dir)

        #parse super( block to initialize the above values
        self.parseSuperBlock()
        #extact the file system
        self.expand_fs(self.extract_dir,self.root_Inode)

    def expand_fs(self, path_name, InodeInstance):
        if stat.S_ISDIR(InodeInstance.mode):
            #create directory if path not exit
            if not os.path.exists(path_name):
                os.makedirs(path_name)
            print(f"{path_name}: is dir")
            self.do_directory(path_name, InodeInstance)

        elif stat.S_ISREG(InodeInstance.mode):
            print(f"{path_name}: is regular file, processing...")
            self.do_file(path_name, InodeInstance);
        else:
            print(f"{path_name} is not dir or regular file.")

    #this function is for debbging
    def dbgPrintPos(self):
        print(f"pos: {self.cramfs_bitstream_buffer.pos/8}")

    def do_file(self, path_name, InodeInstance):
        compressed_file_offset=InodeInstance.offset*4
        output_file_handler=open(path_name, 'wb+')
        if InodeInstance.size>0:
            self.do_extract(path_name, output_file_handler, compressed_file_offset , InodeInstance.size)
        else:
            logging.info(f"{path_name} : file size <0, skip.")

    def do_extract(self, path_name, output_file_handler, compressed_file_offset, file_size):
        blocknr=0

        while file_size:
            #out is decompress data
            out =self.read_block(compressed_file_offset, blocknr, file_size)
            #the file should bigger or as same as page size

            if file_size >= self.PAGE_SIZE:
                if  out != self.PAGE_SIZE: 
                    logging.error("")
            else :
                if out != file_size:
                    logging.error("")
                file_size -= out

                #if opt_extract: 
                if True:
                    number_write_to_file= output_file_handler.write(self.decompressed_data)
                    if ( number_write_to_file< 0):
                        logging.error("123")
                blocknr+=1

    def read_block(self, compressed_file_offset, _blocknr, file_size):
        block_start=0
        blkptr=0 
        block_len=0 
        out=0

        blkptr_offset = compressed_file_offset + _blocknr * 4
        #we have to covert the value to integer manually in python3
        maxblock = int((file_size + self.PAGE_SIZE - 1) / self.PAGE_SIZE*1.0)

        if compressed_file_offset< self.start_data:
            self.start_data=compressed_file_offset



        self.cramfs_bitstream_buffer.pos &=  self.ROMBUFFERMASK
        blkptr=self.romFSRead(blkptr_offset)     #self.romFSRead(blkptr_offset)
        logging.info(f"blkptr {blkptr}")
        uncompressed = (blkptr & self.CRAMFS_BLK_FLAG_UNCOMPRESSED)
        logging.info(f"uncrompreseed {uncompressed}")
        direct = blkptr & self.CRAMFS_BLK_FLAG_DIRECT_PTR
        blkptr &= ~self.CRAMFS_BLK_FLAGS
        print(f"blockptr is {blkptr}")
        '''
         * The block pointer is an absolute start pointer,
		 * shifted by 2 bits. The size is included in the
		 * first 2 bytes of the data block when compressed,
		 * or PAGE_SIZE otherwise.        
        '''

        #beging of direct block
        if direct:
            logging.log("In the direct block")
            block_start = blkptr << self.CRAMFS_BLK_DIRECT_PTR_SHIFT

            if block_start < self.start_data: #start_data is 0xfffffff
                self.start_data = block_start

            if uncompressed:
                logging.log("uncompressed")
                block_len = self.PAGE_SIZE
			    #if last block: cap to file length 
                if _blocknr == maxblock - 1:
                    block_len = file_size % self.PAGE_SIZE
            else:
			    #block_len = *(u16 *) romfs_read(block_start);
                #covert unsigned int to unsigned short 
                '''
                unsigned long cc=0xbadc0ffe;
                unsigned long* p=&cc;   
                printf("%x\n", *(unsigned short*)p);
                unsigned short one = (unsigned short)(cc >> (2 * 8));//left part
                unsigned short two = (unsigned short)(cc % (1 << (2 * 8)));//right part (answer)
                '''
                block_len=block_start%(1<<(2*8))
                block_start += 2
        else:
            logging.info("not in dir")
            logging.info(f"compressed_file_ofsset= {compressed_file_offset}")
            block_start = compressed_file_offset+ maxblock * 4
            if _blocknr:
                block_start = blkptr_offset - 4
            logging.info(f"block_start {block_start}")
            if  block_start & self.CRAMFS_BLK_FLAG_DIRECT_PTR:
			#/* See comments on earlier code. */
                prev_start = block_start
                block_start = prev_start & ~self.CRAMFS_BLK_FLAGS;
                block_start <<= self.CRAMFS_BLK_DIRECT_PTR_SHIFT
                if block_start < self.start_data:
                    self.start_data = block_start
                if prev_start & self.CRAMFS_BLK_FLAG_UNCOMPRESSED:
                    block_start += self.PAGE_SIZE
                else: 
                    #plz check the above comment, how u32 to u16
                    block_len =block_start%(1<<(2*8))
                    block_start += 2 + block_len
            print(f"block_len {block_len}")
            print(f"block_start {block_start}")
            block_start &= ~self.CRAMFS_BLK_FLAGS
            block_len = blkptr - block_start
        #2*4096 byte =8KB
        if block_len > 2*self.PAGE_SIZE or (uncompressed and block_len > self.PAGE_SIZE):
            logging.error("wtf")
        
        if  block_start + block_len > self.end_data:
            self.end_data = block_start + block_len;
        

        if block_len==0:
            pass
        elif uncompressed:
            pass
        else:
            #return the lengt
            out = self.uncompress_block(self.romFSRead(block_start), block_len);
        return out



    #set the self.de





    def uncompress_block(self,src, _block_len):
        compressed_buffer=self.cramfs_bitstream_buffer.read(_block_len*8)
        self.decompressed_data = zlib.decompress(compressed_buffer)
        print(self.decompressed_data[:20])
        return  len(self.decompressed_data)


    def romFSRead(self, block_offset) :
        blockn= block_offset>>self.ROMBUFFER_BITS
        if self.read_buffer_block!=blockn:
            self.read_buffer_block=blockn
        self.cramfs_bitstream_buffer.pos=(blockn << self.ROMBUFFER_BITS)*8
        #to simulate how c lang work
        self.read_buffer=self.cramfs_bitstream_buffer.read( self.ROMBUFFER_SIZE*2*8)
        return int(self.cramfs_bitstream_buffer.pos/8) + (block_offset & self.ROMBUFFERMASK)
        logging.info(f"romFSRead set pos to {block_offset*8}")


    #InodeInstance is instance of Cramfs_inode_class
    def do_directory(self,path_name, InodeInstance):
        #real_offset is byte from file
        NextInode_offset_bytes=InodeInstance.offset*4
        count=InodeInstance.size
        logging.info(f"Current count is {count}")

        while(count>0):
            if len(path_name) > 0:
                new_path_name=path_name+r"/"
            self.cramfs_bitstream_buffer.pos=NextInode_offset_bytes*8
            #remember the bistream recive bit as offset
            buffer_for_NextInode= self.cramfs_bitstream_buffer.read(Cramfs_Inode_class.getStructSizeInBits())
            NextInode=Cramfs_Inode_class(buffer_for_NextInode)
            NextInode_filename_length_bytes=NextInode.namelen*4
            logging.info(f"realnamelen: {NextInode_filename_length_bytes}")
            self.dbgPrintPos()
            #One section consist with One Inode and its filename
            Node_and_name_size=Cramfs_Inode_class.getStructSizeInBytes()+NextInode_filename_length_bytes
            
            #read name as bytes string           
            filename=self.cramfs_bitstream_buffer.read(NextInode_filename_length_bytes*8).bytes
            
            #Cramfs pad filename with \x00 if filename lenth <0, so we need to drop them
            ascii_filename=filename.decode('ascii')
            ascii_filename=ascii_filename.replace('\x00','')
            new_path_name=new_path_name+ascii_filename
            logging.info(f"filename is {ascii_filename}")
            logging.info(f"pathname is {new_path_name}")
            logging.info(f"count is: {count}")

            #count - section_size
            count-=Node_and_name_size
            NextInode_offset_bytes=NextInode_offset_bytes+Node_and_name_size
            #recursive call
            #if ascii_filename=="bin":
            self.expand_fs(new_path_name, NextInode)
  



    def __str__(self):
        return(f"""
=======================superblock==================
*magic={self.magic},
*size={self.size},
*flags={self.flags},
*future={self.future},
*signature={self.signature},
*cramfs_info={self.cramfs_info}
*name={self.name}
*root_Inode={self.root_Inode}
#current offset is {self.cramfs_bitstream_buffer.pos/8}
===================================================
        """)

    def parseSuperBlock(self):
        self.magic=self.cramfs_bitstream_buffer.read(32).hex  
        self.size=self.cramfs_bitstream_buffer.read(32).uint  
        self.flags=self.cramfs_bitstream_buffer.read(32).uint
        self.future=self.cramfs_bitstream_buffer.read(32).uint
        self.signature=self.cramfs_bitstream_buffer.read(8*16).bytes #read 16 bytes as bytesString.
        #print(f"po1 is {self.cramfs_bitstream_buffer.pos/8}")
        info_buffer=self.cramfs_bitstream_buffer.read(4*4*8) #read 4* u32(unsigned int)
        #print(f"pos 2 is {self.cramfs_bitstream_buffer.pos/8}")
        self.cramfs_info=Cramfs_info_class(info_buffer)
        self.name=self.cramfs_bitstream_buffer.read(8*16).bytes #read 16 bytes
        inode_buffer=self.cramfs_bitstream_buffer.read(3*4*8) #read 12 bytes
        self.root_Inode=Cramfs_Inode_class(inode_buffer)
        #
    '''
    struct cramfs_info {
	    u32 crc;
	    u32 edition;
	    u32 blocks;
	    u 32 files;
    };
    '''
class Cramfs_info_class:
    def __init__(self, info_buffer):
        self.info_buffer=info_buffer
        self.crc=None
        self.edition=None
        self.block=None
        self.files=None
        self.parseCramfsInfo()

    def __str__(self):
        return(f"""
    =============Cramfs_info=================
    crc={self.crc}
    edition={self.edition}
    block={self.block}
    files={self.files}
    =========================================
        """)

    @staticmethod
    def getStructSizeInBits():
        return (4*4*8) #return value is bits number (4 *u32)

    def parseCramfsInfo(self):
        self.crc=self.info_buffer.read(32).uint
        self.edition=self.info_buffer.read(32).uint
        self.block=self.info_buffer.read(32).uint
        self.files=self.info_buffer.read(32).uint


'''
struct cramfs_inode {
	u32 mode:CRAMFS_MODE_WIDTH(16 bit), uid:CRAMFS_UID_WIDTH(16 bits);
	/* SIZE for device files is i_rdev */
	u32 size:CRAMFS_SIZE_WIDTH(24 bit), gid:CRAMFS_GID_WIDTH(8 bits);
	/* NAMELEN is the length of the file name, divided by 4 and
           rounded up.  (cramfs doesn't support hard links.) */
	/* OFFSET: For symlinks and non-empty regular files, this
	   contains the offset (divided by 4) of the file data in
	   compressed form (starting with an array of block pointers;
	   see README).  For non-empty directories it is the offset
	   (divided by 4) of the inode of the first file in that
	   directory.  For anything else, offset is zero. */
	   u32 namelen:CRAMFS_NAMELEN_WIDTH(6 bits), offset:CRAMFS_OFFSET_WIDTH(26 bits);
};
'''
class Cramfs_Inode_class:
    def __init__(self, inode_buffer):
        self.inode_buffer=inode_buffer
        self.mode=None
        self.uid=None
        self.size=None
        self.gid=None
        self.namelen=None
        self.offset=None
        self.parseCramfsInode()
    @staticmethod
    def getStructSizeInBits():
        return 3*8*4 # return bits  3* u32 

    @staticmethod
    def getStructSizeInBytes():
        return 3*4
    def __str__(self):
        return(f"""
    =============Cramfs Inode===========
    mode={self.mode}
    uid={self.uid}
    size={self.size}
    gid={self.gid}
    namelen={self.namelen}
    offset={self.offset}
    ====================================
        """)
    '''
    def parseCramfsInode(self):
        self.mode=self.inode_buffer.read(16).uint
        self.uid=self.inode_buffer.read(16).uint
        self.size=self.inode_buffer.read(24).uint
        self.gid=self.inode_buffer.read(8).uint 
        self.namelen=self.inode_buffer.read(6).uint
        self.offset=self.inode_buffer.read(26).uint
    '''
    def parseCramfsInode(self):
        logging.debug("==================parsing inode=====================")
        #read the 4 bytes and store it into array 
        x=[]
        for _ in range(0,4):
            abyte=self.inode_buffer.read(8)
            x.append(abyte.bin)
        #reverse the array(to mitagate the little endian)
        x=x[::-1]

        #concact all the bytes in binary form string
        strings=''.join(x)

        #the value you want will at the end of the string
        #ex: mode offset is 16, the value at the last 16 bin number, and covert it into
        #decimal integer.

        self.mode=(int(strings[-16:],2)) 
        self.uid=(int(strings[0:16],2))
        logging.debug(f"Inode.mode :{self.mode}")
        logging.debug(f"Inode uid: {self.uid}")

        #seconde round
        x=[]
        for _ in range(0,4):
            abyte=self.inode_buffer.read(8)
            x.append(abyte.bin)
        x=x[::-1]
        strings=''.join(x)
        self.size=(int(strings[-24:],2))#get the value revesely
        self.gid=(int(strings[0:8],2))
        logging.debug(f"Inode.size: {self.size}")
        logging.debug(f"Inode.gid: {self.gid}")


        x=[]
        #third round 
        for _ in range(0,4):
            abyte=self.inode_buffer.read(8)
            x.append(abyte.bin)
        x=x[::-1]
        strings="".join(x)
        self.namelen=(int(strings[-6:],2))
        self.offset=(int(strings[0:26],2))
        logging.debug(f"Inode.namelen: {self.namelen}")
        logging.debug(f"Inode.offset: {self.offset}")
        logging.debug("================end parsing inode===================")

        


if __name__=="__main__":
    logging.basicConfig( level=logging.DEBUG)
    a=Cramfs_class("./cramfs-tools/normalcramfs")
    #this will print superblock informaiton
    #print(a)
