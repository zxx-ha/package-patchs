#!/usr/bin/python
########################################################################
#zxx 2017/9/7
# help:
#     python pack_patch.py commit-id patch-number
#sample:
#     python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1
#
#used like git format-patch 
########################################################################
import os
import sys
import string
import time

commit = sys.argv[1]
num = sys.argv[2]
now = time.strftime('%Y%m%d%H%M%S',time.localtime(time.time()))
packagename = 'patch-' + now
SRC = packagename + '/' + 'src'
PATCHS = packagename + '/' + 'patchs'
tmp = "_tmp" + now

#TO DO 

#store patchs
os.system("mkdir -p %s" % PATCHS);
cmd = 'git format-patch' + ' ' + sys.argv[1] + ' ' + sys.argv[2] + ' ' +'-o' + ' ' + PATCHS + ' > ' + tmp
print cmd
os.system(cmd);

#store src
os.system("mkdir -p %s" % SRC);
cmd = 'git log' + ' ' + sys.argv[1] + ' ' + sys.argv[2] + ' ' + "--name-status |egrep '^M\t|^A\t|^D\t'" ' > ' + tmp
os.system(cmd)
reader = open(tmp, 'r')
try:
    while True:
        line = reader.readline()
        if not line:
            cmd = 'zip -r ' + packagename + '.zip ' + packagename + ' > ' + tmp
            os.system(cmd);
            os.system('rm %s -rf' % packagename)
            print '===package end==='
            break
        """
        Deleted file, no need copy, like the following.
        D       arch/arm64/configs/defconfig
        """
        if line[0] == 'D':
            continue
        line = line.strip('^M\t|^A\t|\n') #remove useless character
        cmd = 'cp --parents ' + line + ' ' + SRC 
        print cmd
        os.system(cmd)
except StopIteration:
    print 'StopIteration err'
else: 
    os.system("rm tmp")
    reader.close()
    print 'output: ' + packagename + '.zip'

