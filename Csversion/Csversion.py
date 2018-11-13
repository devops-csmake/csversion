# <copyright>
# (c) Copyright 2018 Cardinal Peak Technologies
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# </copyright>
import CliDriver
import ConfigDriver
import datetime
import glob
import json
import os.path
import re
import yaml
from sys import stdout, stderr

class Output(object):
    def __init__(self):
        self.stream = stdout

    def __del__(self):
        self.close()

    def close(self):
        if self.stream is not stdout and self.stream is not None:
            self.stream.close()
            self.stream = None

    def setFileAsStream(self, filename):
        self.stream = open(filename, 'w')

    def output(self, dictionary):
        self.stream.write(str(dictionary))

class XmlOutput(Output):
    def _outputHelper(self, item, indent=0):
        indentString = " " * 4 * indent
        if issubclass(type(item), dict):
            for key, value in item.iteritems():
                self.stream.write("%s<%s>\n" % (indentString, key))
                self._outputHelper(value, indent+1)
                self.stream.write("%s</%s>\n" % (indentString, key))
        elif issubclass(type(item), list):
            for i in item:
                self.stream.write("%s<item>\n" % indentString)
                self._outputHelper(i, indent+1)
                self.stream.write("%s</item>\n" % indentString)
        else:
            self.stream.write("%s%s\n" % (indentString, str(item)))

    def output(self, dictionary):
        self._outputHelper(dictionary)

class JsonOutput(Output):
    def output(self, dictionary):
        json.dump(dict(dictionary), self.stream)

class YamlOutput(Output):
    def output(self, dictionary):
        yaml.dump(dict(dictionary), self.stream)

OUTPUT_TYPES = {
    'yaml': YamlOutput,
    'json': JsonOutput,
    'xml' : XmlOutput }

class Manifest(dict):
    def __init__(self, filepaths, preprocessed=[]):
        #filepaths is a list of files to load as manifests
        #preprocessed is a list of manifest dictionaries to subsume
        #   into this manifest
        self.preprocessed = []
        for pre in preprocessed:
            m = Manifest([])
            m.update(pre)
            self.preprocessed.append(m)
        if len(filepaths) > 0 or len(preprocessed) > 0:
            self.joinManifests(filepaths)

    def hasMetadata(self):
        return 'product' in self and \
               'metadata' in self['product']

    def tagHasVerisonFull(self, tag):
        return self._hasMetadata() and \
               tag in self['product']['metadata'] and \
               'version-full' in self['product']['metadata'][tag]

    def getVersionFullForTag(self, tag):
        try:
            return self['product']['metadata'][tag]['version-full']
        except KeyError:
            return None

    def hasBuild(self):
        return 'product' in self and \
               'build' in self['product']

    def tagHasTime(self, tag):
        return self._hasBuild() and \
               tag in self['product']['build'] and \
               'time' in self['product']['build'][tag]

    def getTimeForTag(self, tag):
        try:
            return self['product']['capture'][tag]['time']
        except KeyError:
            try:
                return self['product']['build'][tag]['time']
            except KeyError:
                return None

    def compareVersions(self, version1, version2):
        try:
            dotparts1 = version1.split('.')
            dotparts2 = version2.split('.')
            dotzip = zip(dotparts1,dotparts2)
            result = 0
            for part1, part2 in dotzip:
                part1sub = None
                part2sub = None
                if '-' in part1:
                    part1, part1sub = part1.split('-',1)
                if '-' in part2:
                    part2, part2sub = part2.split('-',1)
                try:
                    intpart1 = int(part1)
                    intpart2 = int(part2)
                    result = intpart1 - intpart2
                    if result == 0:
                        intpart1sub = int(part1)
                        intpart2sub = int(part2)
                        result = intpart1sub - intpart2sub
                except (ValueError, TypeError):
                    if part1 == part2:
                        if part1sub > part2sub:
                            return 1
                        elif part1sub < part2sub:
                            return -1
                    else:
                        if part1 > part2:
                            return 1
                        elif part1 < part2:
                            return -1

                if result != 0:
                    break
            return result
        except (TypeError, AttributeError):
            if version1 is None:
                if version2 is None:
                    return 0
                else:
                    return -1
            if version2 is None:
                return 1
            raise

    def convertIsoToDateTime(self, time):
        tz = datetime.timedelta(0)
        if 'Z' in time:
            time = time.split('Z',1)[0]
        elif '+' in time:
            time,zone = time.split('+',1)
            zoneparts = zone.split(':')
            zoneparts.reverse()
            tz = -datetime.timedelta(0,0,0,0,*map(int,zoneparts))
        elif '-' in time:
            time,zone = time.split('-',1)
            zoneparts = zone.split(':')
            zoneparts.reverse()
            tz = datetime.timedelta(0,0,0,0,*map(int,zoneparts))
        return datetime.datetime(*map(int, re.split('[^\d]', time))) + tz

    def compareTimes(self, time1, time2):
        try:
            dttime1 = self.convertIsoToDateTime(time1)
            dttime2 = self.convertIsoToDateTime(time2)
            #Preserve tenths of a second for int comparisons
            return (dttime1 - dttime2).total_seconds()*10.0
        except (TypeError,AttributeError):
            if time1 is None:
                if time2 is None:
                    return 0
                return -1
            if time2 is None:
                return 1
            raise

    def olderKey(self, version, time):
        return "%s__%s" % (version, time)

    def subsumeTag(self, version, date, tag):
        for key, value in self.iteritems():
            for subkey, subvalue in value.iteritems():
                if tag not in subvalue:
                    continue
                olderStash = {}
                if '__older' in subvalue[tag]:
                    olderStash = subvalue[tag].pop('__older')
                verskey = self.olderKey(version,date)
                olderStash[verskey] = dict(subvalue[tag])
                subvalue[tag].clear()
                subvalue[tag]['__older'] = olderStash

    def captureAllTagAges(self):
        if self.hasMetadata():
            return { k:(
                self.getVersionFullForTag(k),
                self.getTimeForTag(k),
                (k,)) for k in self['product']['metadata'].keys() }
        else:
            return {}

    def __getitem__(self, key):
        if type(key) is tuple:
            d = self
            for k in key:
                d = d[k]
            return d
        return dict.__getitem__(self, key)

    def captureAllOldestTagAges(self, specificVersion=None, specificDate=None):
        ages = self.captureAllTagAges()
        if self.hasMetadata():
            for k in ages.keys():
                keyvalue = self['product']['metadata'][k]
                oldestVersion = ages[k][0]
                oldestDate = ages[k][1]
                oldestKeypath = ages[k][2]
                if '__older' in keyvalue:
                    olders = keyvalue['__older'].keys()
                    for old in olders:
                        version, date = old.split('__')
                        if specificVersion is not None and \
                            self.compareVersions(version, specificVersion) != 0:
                                continue
                        if specificDate is not None and \
                            self.compareTimes(date, specificDate) < 0:
                                continue
                        ans = self.compareVersions(oldestVersion, version)
                        if ans == 0:
                            ans = self.compareTimes(oldestDate, date)
                        if ans > 0:
                            oldestVersion = version
                            oldestDate = date
                            oldestKeypath = (k, '__older', old)
                ages[k] = (oldestVersion, oldestDate, oldestKeypath)
        return ages

    def subsumeManifests(self, manifests):
        #Determines if tags are repeated in two or more manifests, and if so
        #  retags the older by:
        #      a) product/metadata/<tag>/version-full
        #      b) product/build/<tag>/time
        #  The newer tag remains untouched
        #  The older tag is transformed by subsuming all the entries
        #  into an "__older" dictionary tagged by <version-full>__<time>
        #  If a manifest is not versioned for a given tag, it's just treated
        #  as a partial manifest and ignored here.
        allTags = {}
        for manifest in manifests:
            if manifest.hasMetadata():
                allTags.update(manifest.captureAllTagAges())

        for tag in allTags.keys():
            #Collect the versions across the manifests for the tag
            taggedManifests = []
            for manifest in manifests:
                version = manifest.getVersionFullForTag(tag)
                time = manifest.getTimeForTag(tag)
                if version is None and time is None:
                    continue
                taggedManifests.append((version, time, manifest))
            latestVersion = version
            latestTime = time
            latestManifest = manifest
            for version, time, manifest in taggedManifests:
                result = manifest.compareVersions(version, latestVersion)
                if result > 0:
                    latestVersion = version
                    latestTime = time
                    latestManifest = manifest
                elif result == 0:
                    if manifest.compareTimes(time, latestTime) > 0:
                        latestVersion = version
                        latestTime = time
                        latestManifest = manifest
            taggedManifests.remove((latestVersion, latestTime, latestManifest))
            for version, time, manifest in taggedManifests:
                manifest.subsumeTag(version, time, tag)

    def joinManifests(self, filepaths):
        if len(filepaths) == 1 and len(self.preprocessed) == 0:
            #Don't do work if there's only one manifest
            self.loadManifest(filepaths[0])
            return
        loadedManifests = list(self.preprocessed)
        for filepath in filepaths:
            loadedManifests.append(Manifest([filepath]))
        if len(loadedManifests) == 1:
            #Don't do work if there's only one manifest
            self.update(loadedManifests[0])
            return
        self.subsumeManifests(loadedManifests)
        for manifest in loadedManifests:
            for key, value in manifest.iteritems():
                if key not in self:
                    self[key] = {}
                for subkey, subvalue in value.iteritems():
                    if subkey not in self[key]:
                        self[key][subkey] = {}
                    for tagkey, tagvalue in subvalue.iteritems():
                        if tagkey not in self[key][subkey]:
                            self[key][subkey][tagkey] = {}
                        fullManifestTag = self[key][subkey][tagkey]
                        if type(tagvalue) is list:
                            #This is for older versions, the list is [key, value]
                            tagvalue = {tagvalue[0] : tagvalue[1:]}
                        fullManifestTag.update(tagvalue)

    def _translateOldToNewProduct(self):
        if 'sources' in self:
            newpackage = {}
            isOld = False
            for package, tags in self['sources'].iteritems():
                #This assumes no mixing of old and new styles
                # in each package entry
                newentry = {}
                for tag, items in tags.iteritems():
                    if '_' in tag or type(items) is list:
                        newitemdict = {}
                        #Reform the items
                        isOld = True
                        if '_' in tag:
                            newtag, rest = tag.split('_', 1)
                        else:
                            newtag = tag
                            rest = '__global'
                        if newtag not in newentry:
                            newentry[newtag] = {}
                        if type(items) is list:
                            #Go from Product:
                            #          tag_context:
                            #              - packageformat
                            #              - packagedata
                            #   Product:
                            #     tag:
                            #       packageformat:
                            #         context:
                            #           packagedata
                            for i in range(0,len(items),2):
                                if items[i] not in newitemdict:
                                    newitemdict[items[i]] = {}
                                newitemdict[items[i]][rest] = items[i+1]
                            newentry[newtag].update(newitemdict)
                        else:
                            try:
                                newentry[newtag].update(items)
                            except TypeError:
                                if '__other' not in newentry[tag]:
                                    newentry[newtag]["__other"] = []
                                newentry[newtag]['__other'].append(items)
                if isOld:
                    newpackage[package]=newentry
                else:
                    break
            if isOld:
                self['sources'] = newpackage

    def loadManifest(self, filepath):
        with open(filepath) as f:
            y = yaml.load(f)
            self.update(y)
            self._translateOldToNewProduct()

    def compareTagDict(self, dict1, dict2):
        if type(dict1) is not type(dict2):
            return False
        if type(dict1) is not dict:
            return dict1 == dict2
        for key, value in dict1.iteritems():
            if key == '__older':
                continue
            if key in dict2:
                if type(dict2) is dict:
                    if not self.compareTagDict(value, dict2[key]):
                        return False
                else:
                    if value != dict2[key]:
                        return False
            else:
                return False
        return True

    def _fillDictToTag(self, key, part, tag, dictionary):
        if key not in dictionary:
            dictionary[key] = {}
        if part not in dictionary[key]:
            dictionary[key][part] = {}
        if tag not in dictionary[key][part]:
            dictionary[key][part][tag] = {}
    
    def diffManifest(self, processor, specificVersion=None, specificDate=None):
        result = {'diff' : {}}
        #Capture the version-full and time of the manifest
        oldests = self.captureAllOldestTagAges(specificVersion, specificDate)
        for key, section in self.iteritems():
            for part, tags in section.iteritems():
                for tag, data in tags.iteritems():
                    if tag in oldests:
                        pathtuple = (key,part) + oldests[tag][2]
                        oldest = data
                        try:
                            oldest = self[pathtuple]
                        except:
                            pass
                        if data is oldest:
                            oldest = {}
                        if not self.compareTagDict(data, oldest):
                            self._fillDictToTag(key,part,tag,result['diff'])
                            tagdiff = result['diff'][key][part][tag]
                            tagdiff['old'] = oldest
                            tagdiff['new'] = dict(data)
                            if '__older' in data:
                                del tagdiff['new']['__older']
                            processor.doHandler((key,part,tag),tagdiff)
        return result

class DiffProcessor(object):
    def __init__(self):
        self.lookups = {}

    def registerHandler(self, path, handler):
        current = self.lookups
        for part in path:
            if part not in current:
                current[part] = {}
            current = current[part]
        current['--call'] = handler

    def doHandler(self, path, data):
        current = self.lookups
        for part in path:
            try:
                current = current[part]
            except KeyError:
                try:
                    current = current['*']
                except KeyError:
                    break
        if '--call' in current:
            return current['--call'](data)
        return False

class CsversionCli(CliDriver.CliDriver):
    def _prepSettings(self):
        origManifests = self.settings['manifests']
        self.settings['manifests'] = [ x.strip() for x in self.settings['manifests'].split(',') ]
        manifestFiles=[]
        for manifest in self.settings['manifests']:
            if os.path.isdir(manifest):
                manifestFiles.extend(glob.glob(os.path.join(manifest,"*.csversion")))
            else:
                manifestFiles.append(manifest)
        self.settings['manifests'] = manifestFiles
        if self.settings['manifests-ignore']:
            self.settings['manifests'] = []
        elif len(self.settings['manifests']) == 0:
            self.log.warning("No manifests specified or found from: %s", origManifests)

        self.settings['csversionfile'] = [ x.strip() for x in self.settings['csversionfile'].split(',') ]

    def _setupProcessedOutput(self):
        self.outputs = []

        #Deal with stdout
        if self.settings['stdout'] in OUTPUT_TYPES:
            self.outputs.append(OUTPUT_TYPES[self.settings['stdout']]())

        #Deal with the other flags
        for outtype, outclass in OUTPUT_TYPES.iteritems():
            if self.settings[outtype] is not None:
                o = outclass()
                o.setFileAsStream(self.settings[outtype])
                self.outputs.append(o)

    def output(self, dictionary):
        for o in self.outputs:
            o.output(dictionary)

    def listVersions(self, manifest):
        output = {'version':{}}
        if manifest.hasMetadata():
            for tag, metadata in manifest['product']['metadata'].iteritems():
                try:
                    name = metadata['name']
                    version = metadata['version-full']
                except KeyError:
                    name = ""
                    version = "No version or name found for tag"
                if tag not in output['version']:
                    output['version'][tag] = []
                output['version'][tag].append({
                    'name' : name,
                    'version' : version })
        self.output(output)

    def _getDiffProcessor(self):
        return DiffProcessor()

    def _realmain(self):
        self.diffprocessor = self._getDiffProcessor()
        self._prepSettings()
        self._setupProcessedOutput()

        preprocessed = []
        if self.settings['capture']:
            configs = self.settings['csversionfile']
            newmanifest = {}
            preprocessed.append(newmanifest)
            execer = ConfigDriver.ConfigDriver(
                configs,
                self.log,
                newmanifest )
            execer.execute()
        self.manifest = Manifest(self.settings['manifests'], preprocessed)
        if self.settings['diff']:
            self.output(self.manifest.diffManifest(
                self.diffprocessor,
                self.settings['diff-version'],
                self.settings['diff-date']))
            return
        if self.settings['verbose']:
            self.output(self.manifest)
        else:
            self.listVersions(self.manifest)
