import fcntl
import hashlib
import os
import re
import subprocess
import errno
import sys
from arvados.collection import *

def clear_tmpdir(path=None):
    """
    Ensure the given directory (or TASK_TMPDIR if none given)
    exists and is empty.
    """
    if path == None:
        path = arvados.current_task().tmpdir
    if os.path.exists(path):
        p = subprocess.Popen(['rm', '-rf', path])
        stdout, stderr = p.communicate(None)
        if p.returncode != 0:
            raise Exception('rm -rf %s: %s' % (path, stderr))
    os.mkdir(path)

def run_command(execargs, **kwargs):
    kwargs.setdefault('stdin', subprocess.PIPE)
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', sys.stderr)
    kwargs.setdefault('close_fds', True)
    kwargs.setdefault('shell', False)
    p = subprocess.Popen(execargs, **kwargs)
    stdoutdata, stderrdata = p.communicate(None)
    if p.returncode != 0:
        raise errors.CommandFailedError(
            "run_command %s exit %d:\n%s" %
            (execargs, p.returncode, stderrdata))
    return stdoutdata, stderrdata

def git_checkout(url, version, path):
    if not re.search('^/', path):
        path = os.path.join(arvados.current_job().tmpdir, path)
    if not os.path.exists(path):
        run_command(["git", "clone", url, path],
                    cwd=os.path.dirname(path))
    run_command(["git", "checkout", version],
                cwd=path)
    return path

def tar_extractor(path, decompress_flag):
    return subprocess.Popen(["tar",
                             "-C", path,
                             ("-x%sf" % decompress_flag),
                             "-"],
                            stdout=None,
                            stdin=subprocess.PIPE, stderr=sys.stderr,
                            shell=False, close_fds=True)

def tarball_extract(tarball, path):
    """Retrieve a tarball from Keep and extract it to a local
    directory.  Return the absolute path where the tarball was
    extracted. If the top level of the tarball contained just one
    file or directory, return the absolute path of that single
    item.

    tarball -- collection locator
    path -- where to extract the tarball: absolute, or relative to job tmp
    """
    if not re.search('^/', path):
        path = os.path.join(arvados.current_job().tmpdir, path)
    lockfile = open(path + '.lock', 'w')
    fcntl.flock(lockfile, fcntl.LOCK_EX)
    try:
        os.stat(path)
    except OSError:
        os.mkdir(path)
    already_have_it = False
    try:
        if os.readlink(os.path.join(path, '.locator')) == tarball:
            already_have_it = True
    except OSError:
        pass
    if not already_have_it:

        # emulate "rm -f" (i.e., if the file does not exist, we win)
        try:
            os.unlink(os.path.join(path, '.locator'))
        except OSError:
            if os.path.exists(os.path.join(path, '.locator')):
                os.unlink(os.path.join(path, '.locator'))

        for f in CollectionReader(tarball).all_files():
            if re.search('\.(tbz|tar.bz2)$', f.name()):
                p = tar_extractor(path, 'j')
            elif re.search('\.(tgz|tar.gz)$', f.name()):
                p = tar_extractor(path, 'z')
            elif re.search('\.tar$', f.name()):
                p = tar_extractor(path, '')
            else:
                raise errors.AssertionError(
                    "tarball_extract cannot handle filename %s" % f.name())
            while True:
                buf = f.read(2**20)
                if len(buf) == 0:
                    break
                p.stdin.write(buf)
            p.stdin.close()
            p.wait()
            if p.returncode != 0:
                lockfile.close()
                raise errors.CommandFailedError(
                    "tar exited %d" % p.returncode)
        os.symlink(tarball, os.path.join(path, '.locator'))
    tld_extracts = filter(lambda f: f != '.locator', os.listdir(path))
    lockfile.close()
    if len(tld_extracts) == 1:
        return os.path.join(path, tld_extracts[0])
    return path

def zipball_extract(zipball, path):
    """Retrieve a zip archive from Keep and extract it to a local
    directory.  Return the absolute path where the archive was
    extracted. If the top level of the archive contained just one
    file or directory, return the absolute path of that single
    item.

    zipball -- collection locator
    path -- where to extract the archive: absolute, or relative to job tmp
    """
    if not re.search('^/', path):
        path = os.path.join(arvados.current_job().tmpdir, path)
    lockfile = open(path + '.lock', 'w')
    fcntl.flock(lockfile, fcntl.LOCK_EX)
    try:
        os.stat(path)
    except OSError:
        os.mkdir(path)
    already_have_it = False
    try:
        if os.readlink(os.path.join(path, '.locator')) == zipball:
            already_have_it = True
    except OSError:
        pass
    if not already_have_it:

        # emulate "rm -f" (i.e., if the file does not exist, we win)
        try:
            os.unlink(os.path.join(path, '.locator'))
        except OSError:
            if os.path.exists(os.path.join(path, '.locator')):
                os.unlink(os.path.join(path, '.locator'))

        for f in CollectionReader(zipball).all_files():
            if not re.search('\.zip$', f.name()):
                raise errors.NotImplementedError(
                    "zipball_extract cannot handle filename %s" % f.name())
            zip_filename = os.path.join(path, os.path.basename(f.name()))
            zip_file = open(zip_filename, 'wb')
            while True:
                buf = f.read(2**20)
                if len(buf) == 0:
                    break
                zip_file.write(buf)
            zip_file.close()
            
            p = subprocess.Popen(["unzip",
                                  "-q", "-o",
                                  "-d", path,
                                  zip_filename],
                                 stdout=None,
                                 stdin=None, stderr=sys.stderr,
                                 shell=False, close_fds=True)
            p.wait()
            if p.returncode != 0:
                lockfile.close()
                raise errors.CommandFailedError(
                    "unzip exited %d" % p.returncode)
            os.unlink(zip_filename)
        os.symlink(zipball, os.path.join(path, '.locator'))
    tld_extracts = filter(lambda f: f != '.locator', os.listdir(path))
    lockfile.close()
    if len(tld_extracts) == 1:
        return os.path.join(path, tld_extracts[0])
    return path

def collection_extract(collection, path, files=[], decompress=True):
    """Retrieve a collection from Keep and extract it to a local
    directory.  Return the absolute path where the collection was
    extracted.

    collection -- collection locator
    path -- where to extract: absolute, or relative to job tmp
    """
    matches = re.search(r'^([0-9a-f]+)(\+[\w@]+)*$', collection)
    if matches:
        collection_hash = matches.group(1)
    else:
        collection_hash = hashlib.md5(collection).hexdigest()
    if not re.search('^/', path):
        path = os.path.join(arvados.current_job().tmpdir, path)
    lockfile = open(path + '.lock', 'w')
    fcntl.flock(lockfile, fcntl.LOCK_EX)
    try:
        os.stat(path)
    except OSError:
        os.mkdir(path)
    already_have_it = False
    try:
        if os.readlink(os.path.join(path, '.locator')) == collection_hash:
            already_have_it = True
    except OSError:
        pass

    # emulate "rm -f" (i.e., if the file does not exist, we win)
    try:
        os.unlink(os.path.join(path, '.locator'))
    except OSError:
        if os.path.exists(os.path.join(path, '.locator')):
            os.unlink(os.path.join(path, '.locator'))

    files_got = []
    for s in CollectionReader(collection).all_streams():
        stream_name = s.name()
        for f in s.all_files():
            if (files == [] or
                ((f.name() not in files_got) and
                 (f.name() in files or
                  (decompress and f.decompressed_name() in files)))):
                outname = f.decompressed_name() if decompress else f.name()
                files_got += [outname]
                if os.path.exists(os.path.join(path, stream_name, outname)):
                    continue
                mkdir_dash_p(os.path.dirname(os.path.join(path, stream_name, outname)))
                outfile = open(os.path.join(path, stream_name, outname), 'wb')
                for buf in (f.readall_decompressed() if decompress
                            else f.readall()):
                    outfile.write(buf)
                outfile.close()
    if len(files_got) < len(files):
        raise errors.AssertionError(
            "Wanted files %s but only got %s from %s" %
            (files, files_got,
             [z.name() for z in CollectionReader(collection).all_files()]))
    os.symlink(collection_hash, os.path.join(path, '.locator'))

    lockfile.close()
    return path

def mkdir_dash_p(path):
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno == errno.EEXIST and os.path.isdir(path):
                # It is not an error if someone else creates the
                # directory between our exists() and makedirs() calls.
                pass
            else:
                raise

def stream_extract(stream, path, files=[], decompress=True):
    """Retrieve a stream from Keep and extract it to a local
    directory.  Return the absolute path where the stream was
    extracted.

    stream -- StreamReader object
    path -- where to extract: absolute, or relative to job tmp
    """
    if not re.search('^/', path):
        path = os.path.join(arvados.current_job().tmpdir, path)
    lockfile = open(path + '.lock', 'w')
    fcntl.flock(lockfile, fcntl.LOCK_EX)
    try:
        os.stat(path)
    except OSError:
        os.mkdir(path)

    files_got = []
    for f in stream.all_files():
        if (files == [] or
            ((f.name() not in files_got) and
             (f.name() in files or
              (decompress and f.decompressed_name() in files)))):
            outname = f.decompressed_name() if decompress else f.name()
            files_got += [outname]
            if os.path.exists(os.path.join(path, outname)):
                os.unlink(os.path.join(path, outname))
            mkdir_dash_p(os.path.dirname(os.path.join(path, outname)))
            outfile = open(os.path.join(path, outname), 'wb')
            for buf in (f.readall_decompressed() if decompress
                        else f.readall()):
                outfile.write(buf)
            outfile.close()
    if len(files_got) < len(files):
        raise errors.AssertionError(
            "Wanted files %s but only got %s from %s" %
            (files, files_got, [z.name() for z in stream.all_files()]))
    lockfile.close()
    return path

def listdir_recursive(dirname, base=None):
    allfiles = []
    for ent in sorted(os.listdir(dirname)):
        ent_path = os.path.join(dirname, ent)
        ent_base = os.path.join(base, ent) if base else ent
        if os.path.isdir(ent_path):
            allfiles += listdir_recursive(ent_path, ent_base)
        else:
            allfiles += [ent_base]
    return allfiles
