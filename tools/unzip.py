import zipfile,sys
z=zipfile.ZipFile(sys.argv[1])
for i in z.infolist():
    n=i.filename.replace(chr(92),'/')
    assert not n.startswith('/') and '..' not in n.split('/'),n
    print(i.file_size,n)
z.extractall(sys.argv[2])
