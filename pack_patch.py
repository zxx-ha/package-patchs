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

try:
    commit = sys.argv[1]
    num = sys.argv[2]
except IndexError:
    print "cmd err!!!"
    print "sample:"
    print "python pack_patch.py commit-id patch-number"
    print "python pack_patch.py 1d17982938f5808205debf052cab10381f6e5282 -1"
    sys.exit()

now = time.strftime('%Y%m%d%H%M%S',time.localtime(time.time()))
packagename = 'patch-' + now
SRC = packagename + '/' + 'src'
PATCHS = packagename + '/' + 'patchs'

if os.system("git log %s %s > %s" % (commit, num, now)):
    print "commit-id %s does not exist!!!" % commit
    os.system("rm %s" % now)
    sys.exit()
#TO DO 

#store patchs
os.system("mkdir -p %s" % PATCHS);
os.system("git format-patch %s %s -o %s > %s" % (sys.argv[1], sys.argv[2], PATCHS, now));

#store src
os.system("mkdir -p %s" % SRC);
os.system("git log %s %s --name-status |egrep '^M\t|^A\t|^D\t' > %s" % (sys.argv[1], sys.argv[2], now))
reader = open(now, 'r')
try:
    while True:
        line = reader.readline()
        if not line:
            os.system("zip -r %s.zip %s" % (packagename, packagename));
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
        os.system("cp --parents %s %s" % (line, SRC))
except StopIteration:
    print 'StopIteration err'
else: 
    os.system("rm %s" % now)
    reader.close()
    print 'output: ' + packagename + '.zip'

