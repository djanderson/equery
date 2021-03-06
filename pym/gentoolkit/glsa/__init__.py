# $Header$

# This program is licensed under the GPL, version 2

# WARNING: this code is only tested by a few people and should NOT be used
# on production systems at this stage. There are possible security holes and probably
# bugs in this code. If you test it please report ANY success or failure to
# me (genone@gentoo.org).

# The following planned features are currently on hold:
# - getting GLSAs from http/ftp servers (not really useful without the fixed ebuilds)
# - GPG signing/verification (until key policy is clear)

from __future__ import unicode_literals

__author__ = "Marius Mauch <genone@gentoo.org>"


import sys
import os
try:
    from urllib import urlopen
except ImportError:
    from urllib.request import urlopen
import codecs
import re
import operator
import xml.dom.minidom
from io import StringIO
from functools import reduce

if sys.version_info[0:2] < (2,3):
	raise NotImplementedError("Python versions below 2.3 have broken XML code " \
								+"and are not supported")

try:
	import portage
except ImportError:
	sys.path.insert(0, "/usr/lib/portage/pym")
	import portage


# Note: the space for rgt and rlt is important !!
opMapping = {"le": "<=", "lt": "<", "eq": "=", "gt": ">", "ge": ">=",
			 "rge": ">=~", "rle": "<=~", "rgt": " >~", "rlt": " <~"}
NEWLINE_ESCAPE = "!;\\n"	# some random string to mark newlines that should be preserved
SPACE_ESCAPE = "!;_"		# some random string to mark spaces that should be preserved

def center(text, width):
	"""
	Returns a string containing I{text} that is padded with spaces on both
	sides. If C{len(text) >= width} I{text} is returned unchanged.

	@type	text: String
	@param	text: the text to be embedded
	@type	width: Integer
	@param	width: the minimum length of the returned string
	@rtype:		String
	@return:	the expanded string or I{text}
	"""
	if len(text) >= width:
		return text
	margin = (width-len(text))/2
	rValue = " "*margin
	rValue += text
	if 2*margin + len(text) == width:
		rValue += " "*margin
	elif 2*margin + len(text) + 1 == width:
		rValue += " "*(margin+1)
	return rValue


def wrap(text, width, caption=""):
	"""
	Wraps the given text at column I{width}, optionally indenting
	it so that no text is under I{caption}. It's possible to encode
	hard linebreaks in I{text} with L{NEWLINE_ESCAPE}.

	@type	text: String
	@param	text: the text to be wrapped
	@type	width: Integer
	@param	width: the column at which the text should be wrapped
	@type	caption: String
	@param	caption: this string is inserted at the beginning of the
					 return value and the paragraph is indented up to
					 C{len(caption)}.
	@rtype:		String
	@return:	the wrapped and indented paragraph
	"""
	rValue = ""
	line = caption
	text = text.replace(2*NEWLINE_ESCAPE, NEWLINE_ESCAPE+" "+NEWLINE_ESCAPE)
	words = text.split()
	indentLevel = len(caption)+1

	for w in words:
		if line[-1] == "\n":
			rValue += line
			line = " "*indentLevel
		if len(line)+len(w.replace(NEWLINE_ESCAPE, ""))+1 > width:
			rValue += line+"\n"
			line = " "*indentLevel+w.replace(NEWLINE_ESCAPE, "\n")
		elif w.find(NEWLINE_ESCAPE) >= 0:
			if len(line.strip()) > 0:
				rValue += line+" "+w.replace(NEWLINE_ESCAPE, "\n")
			else:
				rValue += line+w.replace(NEWLINE_ESCAPE, "\n")
			line = " "*indentLevel
		else:
			if len(line.strip()) > 0:
				line += " "+w
			else:
				line += w
	if len(line) > 0:
		rValue += line.replace(NEWLINE_ESCAPE, "\n")
	rValue = rValue.replace(SPACE_ESCAPE, " ")
	return rValue

def checkconfig(myconfig):
	"""
	takes a portage.config instance and adds GLSA specific keys if
	they are not present. TO-BE-REMOVED (should end up in make.*)
	"""
	mysettings = {
		"GLSA_DIR": portage.settings["PORTDIR"]+"/metadata/glsa/",
		"GLSA_PREFIX": "glsa-",
		"GLSA_SUFFIX": ".xml",
		"CHECKFILE": "/var/lib/portage/glsa_injected",
		"GLSA_SERVER": "www.gentoo.org/security/en/glsa/",	# not completely implemented yet
		"CHECKMODE": "local",								# not completely implemented yet
		"PRINTWIDTH": "76"
	}
	for k in mysettings.keys():
		if k not in myconfig:
			myconfig[k] = mysettings[k]
	return myconfig

def get_glsa_list(repository, myconfig):
	"""
	Returns a list of all available GLSAs in the given repository
	by comparing the filelist there with the pattern described in
	the config.

	@type	repository: String
	@param	repository: The directory or an URL that contains GLSA files
						(Note: not implemented yet)
	@type	myconfig: portage.config
	@param	myconfig: a GLSA aware config instance (see L{checkconfig})

	@rtype:		List of Strings
	@return:	a list of GLSA IDs in this repository
	"""
	# TODO: remote fetch code for listing

	rValue = []

	if not os.access(repository, os.R_OK):
		return []
	dirlist = os.listdir(repository)
	prefix = myconfig["GLSA_PREFIX"]
	suffix = myconfig["GLSA_SUFFIX"]

	for f in dirlist:
		try:
			if f[:len(prefix)] == prefix and f[-1*len(suffix):] == suffix:
				rValue.append(f[len(prefix):-1*len(suffix)])
		except IndexError:
			pass
	return rValue

def getListElements(listnode):
	"""
	Get all <li> elements for a given <ol> or <ul> node.

	@type	listnode: xml.dom.Node
	@param	listnode: <ul> or <ol> list to get the elements for
	@rtype:		List of Strings
	@return:	a list that contains the value of the <li> elements
	"""
	if not listnode.nodeName in ["ul", "ol"]:
		raise GlsaFormatException("Invalid function call: listnode is not <ul> or <ol>")
	rValue = [getText(li, format="strip") \
		for li in listnode.childNodes \
		if li.nodeType == xml.dom.Node.ELEMENT_NODE]
	return rValue

def getText(node, format, textfd = None):
	"""
	This is the main parser function. It takes a node and traverses
	recursive over the subnodes, getting the text of each (and the
	I{link} attribute for <uri> and <mail>). Depending on the I{format}
	parameter the text might be formatted by adding/removing newlines,
	tabs and spaces. This function is only useful for the GLSA DTD,
	it's not applicable for other DTDs.

	@type	node: xml.dom.Node
	@param	node: the root node to start with the parsing
	@type	format: String
	@param	format: this should be either I{strip}, I{keep} or I{xml}
					I{keep} just gets the text and does no formatting.
					I{strip} replaces newlines and tabs with spaces and
					replaces multiple spaces with one space.
					I{xml} does some more formatting, depending on the
					type of the encountered nodes.
	@type	textfd: writable file-like object
	@param	textfd: the file-like object to write the output to
	@rtype:		String
	@return:	the (formatted) content of the node and its subnodes
			except if textfd was not none
	"""
	if not textfd:
		textfd = StringIO()
		returnNone = False
	else:
		returnNone = True
	if format in ["strip", "keep"]:
		if node.nodeName in ["uri", "mail"]:
			textfd.write(node.childNodes[0].data+": "+node.getAttribute("link"))
		else:
			for subnode in node.childNodes:
				if subnode.nodeName == "#text":
					textfd.write(subnode.data)
				else:
					getText(subnode, format, textfd)
	else: # format = "xml"
		for subnode in node.childNodes:
			if subnode.nodeName == "p":
				for p_subnode in subnode.childNodes:
					if p_subnode.nodeName == "#text":
						textfd.write(p_subnode.data.strip())
					elif p_subnode.nodeName in ["uri", "mail"]:
						textfd.write(p_subnode.childNodes[0].data)
						textfd.write(" ( "+p_subnode.getAttribute("link")+" )")
				textfd.write(NEWLINE_ESCAPE)
			elif subnode.nodeName == "ul":
				for li in getListElements(subnode):
					textfd.write("-"+SPACE_ESCAPE+li+NEWLINE_ESCAPE+" ")
			elif subnode.nodeName == "ol":
				i = 0
				for li in getListElements(subnode):
					i = i+1
					textfd.write(str(i)+"."+SPACE_ESCAPE+li+NEWLINE_ESCAPE+" ")
			elif subnode.nodeName == "code":
				textfd.write(getText(subnode, format="keep").lstrip().replace("\n", NEWLINE_ESCAPE))
				textfd.write(NEWLINE_ESCAPE)
			elif subnode.nodeName == "#text":
				textfd.write(subnode.data)
			else:
				raise GlsaFormatException("Invalid Tag found: ", subnode.nodeName)
	if returnNone:
		return None
	rValue = textfd.getvalue()
	if format == "strip":
		rValue = rValue.strip(" \n\t")
		rValue = re.sub("[\s]{2,}", " ", rValue)
	return rValue

def getMultiTagsText(rootnode, tagname, format):
	"""
	Returns a list with the text of all subnodes of type I{tagname}
	under I{rootnode} (which itself is not parsed) using the given I{format}.

	@type	rootnode: xml.dom.Node
	@param	rootnode: the node to search for I{tagname}
	@type	tagname: String
	@param	tagname: the name of the tags to search for
	@type	format: String
	@param	format: see L{getText}
	@rtype:		List of Strings
	@return:	a list containing the text of all I{tagname} childnodes
	"""
	rValue = [getText(e, format) \
		for e in rootnode.getElementsByTagName(tagname)]
	return rValue

def makeAtom(pkgname, versionNode):
	"""
	creates from the given package name and information in the
	I{versionNode} a (syntactical) valid portage atom.

	@type	pkgname: String
	@param	pkgname: the name of the package for this atom
	@type	versionNode: xml.dom.Node
	@param	versionNode: a <vulnerable> or <unaffected> Node that
						 contains the version information for this atom
	@rtype:		String
	@return:	the portage atom
	"""
	rValue = opMapping[versionNode.getAttribute("range")] \
				+ pkgname \
				+ "-" + getText(versionNode, format="strip")
	try:
		slot = versionNode.getAttribute("slot").strip()
	except KeyError:
		pass
	else:
		if slot and slot != "*":
			rValue += ":" + slot
	return str(rValue)

def makeVersion(versionNode):
	"""
	creates from the information in the I{versionNode} a
	version string (format <op><version>).

	@type	versionNode: xml.dom.Node
	@param	versionNode: a <vulnerable> or <unaffected> Node that
						 contains the version information for this atom
	@rtype:		String
	@return:	the version string
	"""
	rValue = opMapping[versionNode.getAttribute("range")] \
			+getText(versionNode, format="strip")
	try:
		slot = versionNode.getAttribute("slot").strip()
	except KeyError:
		pass
	else:
		if slot and slot != "*":
			rValue += ":" + slot
	return rValue

def match(atom, portdbname, match_type="default"):
	"""
	wrapper that calls revisionMatch() or portage.dbapi.match() depending on
	the given atom.

	@type	atom: string
	@param	atom: a <~ or >~ atom or a normal portage atom that contains the atom to match against
	@type	portdb: portage.dbapi
	@param	portdb:	one of the portage databases to use as information source
	@type	match_type: string
	@param	match_type: if != "default" passed as first argument to dbapi.xmatch
				to apply the wanted visibility filters

	@rtype:		list of strings
	@return:	a list with the matching versions
	"""
	db = portage.db[portage.root][portdbname].dbapi
	if atom[2] == "~":
		return revisionMatch(atom, db, match_type=match_type)
	elif match_type == "default" or not hasattr(db, "xmatch"):
		return db.match(atom)
	else:
		return db.xmatch(match_type, atom)

def revisionMatch(revisionAtom, portdb, match_type="default"):
	"""
	handler for the special >~, >=~, <=~ and <~ atoms that are supposed to behave
	as > and < except that they are limited to the same version, the range only
	applies to the revision part.

	@type	revisionAtom: string
	@param	revisionAtom: a <~ or >~ atom that contains the atom to match against
	@type	portdb: portage.dbapi
	@param	portdb:	one of the portage databases to use as information source
	@type	match_type: string
	@param	match_type: if != "default" passed as first argument to portdb.xmatch
				to apply the wanted visibility filters

	@rtype:		list of strings
	@return:	a list with the matching versions
	"""
	if match_type == "default" or not hasattr(portdb, "xmatch"):
		if ":" in revisionAtom:
			mylist = portdb.match(re.sub(r'-r[0-9]+(:[^ ]+)?$', r'\1', revisionAtom[2:]))
		else:
			mylist = portdb.match(re.sub("-r[0-9]+$", "", revisionAtom[2:]))
	else:
		if ":" in revisionAtom:
			mylist = portdb.xmatch(match_type, re.sub(r'-r[0-9]+(:[^ ]+)?$', r'\1', revisionAtom[2:]))
		else:
			mylist = portdb.xmatch(match_type, re.sub("-r[0-9]+$", "", revisionAtom[2:]))
	rValue = []
	for v in mylist:
		r1 = portage.pkgsplit(v)[-1][1:]
		r2 = portage.pkgsplit(revisionAtom[3:])[-1][1:]
		if eval(r1+" "+revisionAtom[0:2]+" "+r2):
			rValue.append(v)
	return rValue


def getMinUpgrade(vulnerableList, unaffectedList, minimize=True):
	"""
	Checks if the systemstate is matching an atom in
	I{vulnerableList} and returns string describing
	the lowest version for the package that matches an atom in
	I{unaffectedList} and is greater than the currently installed
	version. It will return an empty list if the system is affected,
	and no upgrade is possible or None if the system is not affected.
	Both I{vulnerableList} and I{unaffectedList} should have the
	same base package.

	@type	vulnerableList: List of Strings
	@param	vulnerableList: atoms matching vulnerable package versions
	@type	unaffectedList: List of Strings
	@param	unaffectedList: atoms matching unaffected package versions
	@type	minimize:	Boolean
	@param	minimize:	True for a least-change upgrade, False for emerge-like algorithm

	@rtype:		String | None
	@return:	the lowest unaffected version that is greater than
				the installed version.
	"""
	rValue = ""
	v_installed = reduce(operator.add, [match(v, "vartree") for v in vulnerableList], [])
	u_installed = reduce(operator.add, [match(u, "vartree") for u in unaffectedList], [])

	# remove all unaffected atoms from vulnerable list
	v_installed = list(set(v_installed).difference(set(u_installed)))

	if not v_installed:
		return None

	# this tuple holds all vulnerable atoms, and the related upgrade atom
	vuln_update = []
	avail_updates = set()
	for u in unaffectedList:
		# TODO: This had match_type="match-all" before. I don't think it should
		# since we disregarded masked items later anyway (match(=rValue, "porttree"))
		avail_updates.update(match(u, "porttree"))
	# if an atom is already installed, we should not consider it for upgrades
	avail_updates.difference_update(u_installed)

	for vuln in v_installed:
		update = ""
		for c in avail_updates:
			c_pv = portage.catpkgsplit(c)
			i_pv = portage.catpkgsplit(vuln)
			if portage.pkgcmp(c_pv[1:], i_pv[1:]) > 0 \
					and (update == "" \
						or (minimize ^ (portage.pkgcmp(c_pv[1:], portage.catpkgsplit(update)[1:]) > 0))) \
					and portage.db[portage.root]["porttree"].dbapi.aux_get(c, ["SLOT"]) == portage.db[portage.root]["vartree"].dbapi.aux_get(vuln, ["SLOT"]):
				update = c_pv[0]+"/"+c_pv[1]+"-"+c_pv[2]
				if c_pv[3] != "r0":		# we don't like -r0 for display
					update += "-"+c_pv[3]
		vuln_update.append([vuln, update])

	return vuln_update

def format_date(datestr):
	"""
	Takes a date (announced, revised) date from a GLSA and formats
	it as readable text (i.e. "January 1, 2008").

	@type	date: String
	@param	date: the date string to reformat
	@rtype:		String
	@return:	a reformatted string, or the original string
				if it cannot be reformatted.
	"""
	splitdate = datestr.split("-", 2)
	if len(splitdate) != 3:
		return datestr

	# This cannot raise an error as we use () instead of []
	splitdate = (int(x) for x in splitdate)

	from datetime import date
	try:
		d = date(*splitdate)
	except ValueError:
		return datestr

	# TODO We could format to local date format '%x' here?
	return d.strftime("%B %d, %Y")

# simple Exception classes to catch specific errors
class GlsaTypeException(Exception):
	def __init__(self, doctype):
		Exception.__init__(self, "wrong DOCTYPE: %s" % doctype)

class GlsaFormatException(Exception):
	pass

class GlsaArgumentException(Exception):
	pass

# GLSA xml data wrapper class
class Glsa:
	"""
	This class is a wrapper for the XML data and provides methods to access
	and display the contained data.
	"""
	def __init__(self, myid, myconfig):
		"""
		Simple constructor to set the ID, store the config and gets the
		XML data by calling C{self.read()}.

		@type	myid: String
		@param	myid: String describing the id for the GLSA object (standard
					  GLSAs have an ID of the form YYYYMM-nn) or an existing
					  filename containing a GLSA.
		@type	myconfig: portage.config
		@param	myconfig: the config that should be used for this object.
		"""
		if re.match(r'\d{6}-\d{2}', myid):
			self.type = "id"
		elif os.path.exists(myid):
			self.type = "file"
		else:
			raise GlsaArgumentException("Given ID "+myid+" isn't a valid GLSA ID or filename.")
		self.nr = myid
		self.config = myconfig
		self.read()

	def read(self):
		"""
		Here we build the filename from the config and the ID and pass
		it to urllib to fetch it from the filesystem or a remote server.

		@rtype:		None
		@return:	None
		"""
		if self.config["CHECKMODE"] == "local":
			repository = "file://" + self.config["GLSA_DIR"]
		else:
			repository = self.config["GLSA_SERVER"]
		if self.type == "file":
			myurl = "file://"+self.nr
		else:
			myurl = repository + self.config["GLSA_PREFIX"] + str(self.nr) + self.config["GLSA_SUFFIX"]
		self.parse(urlopen(myurl))
		return None

	def parse(self, myfile):
		"""
		This method parses the XML file and sets up the internal data
		structures by calling the different helper functions in this
		module.

		@type	myfile: String
		@param	myfile: Filename to grab the XML data from
		@rtype:		None
		@returns:	None
		"""
		self.DOM = xml.dom.minidom.parse(myfile)
		if not self.DOM.doctype:
			raise GlsaTypeException(None)
		elif self.DOM.doctype.systemId == "http://www.gentoo.org/dtd/glsa.dtd":
			self.dtdversion = 0
		elif self.DOM.doctype.systemId == "http://www.gentoo.org/dtd/glsa-2.dtd":
			self.dtdversion = 2
		else:
			raise GlsaTypeException(self.DOM.doctype.systemId)
		myroot = self.DOM.getElementsByTagName("glsa")[0]
		if self.type == "id" and myroot.getAttribute("id") != self.nr:
			raise GlsaFormatException("filename and internal id don't match:" + myroot.getAttribute("id") + " != " + self.nr)

		# the simple (single, required, top-level, #PCDATA) tags first
		self.title = getText(myroot.getElementsByTagName("title")[0], format="strip")
		self.synopsis = getText(myroot.getElementsByTagName("synopsis")[0], format="strip")
		self.announced = format_date(getText(myroot.getElementsByTagName("announced")[0], format="strip"))

		# Support both formats of revised:
		# <revised>December 30, 2007: 02</revised>
		# <revised count="2">2007-12-30</revised>
		revisedEl = myroot.getElementsByTagName("revised")[0]
		self.revised = getText(revisedEl, format="strip")
		count = revisedEl.attributes.get("count")
		if count is None:
			if self.revised.find(":") >= 0:
				(self.revised, count) = self.revised.split(":")
			else:
				count = 1

		self.revised = format_date(self.revised)

		try:
			self.count = int(count)
		except ValueError:
			# TODO should this rais a GlsaFormatException?
			self.count = 1

		# now the optional and 0-n toplevel, #PCDATA tags and references
		try:
			self.access = getText(myroot.getElementsByTagName("access")[0], format="strip")
		except IndexError:
			self.access = ""
		self.bugs = getMultiTagsText(myroot, "bug", format="strip")
		self.references = getMultiTagsText(myroot.getElementsByTagName("references")[0], "uri", format="keep")

		# and now the formatted text elements
		self.description = getText(myroot.getElementsByTagName("description")[0], format="xml")
		self.workaround = getText(myroot.getElementsByTagName("workaround")[0], format="xml")
		self.resolution = getText(myroot.getElementsByTagName("resolution")[0], format="xml")
		self.impact_text = getText(myroot.getElementsByTagName("impact")[0], format="xml")
		self.impact_type = myroot.getElementsByTagName("impact")[0].getAttribute("type")
		try:
			self.background = getText(myroot.getElementsByTagName("background")[0], format="xml")
		except IndexError:
			self.background = ""

		# finally the interesting tags (product, affected, package)
		self.glsatype = myroot.getElementsByTagName("product")[0].getAttribute("type")
		self.product = getText(myroot.getElementsByTagName("product")[0], format="strip")
		self.affected = myroot.getElementsByTagName("affected")[0]
		self.packages = {}
		for p in self.affected.getElementsByTagName("package"):
			name = p.getAttribute("name")
			if name not in self.packages:
				self.packages[name] = []
			tmp = {}
			tmp["arch"] = p.getAttribute("arch")
			tmp["auto"] = (p.getAttribute("auto") == "yes")
			tmp["vul_vers"] = [makeVersion(v) for v in p.getElementsByTagName("vulnerable")]
			tmp["unaff_vers"] = [makeVersion(v) for v in p.getElementsByTagName("unaffected")]
			tmp["vul_atoms"] = [makeAtom(name, v) for v in p.getElementsByTagName("vulnerable")]
			tmp["unaff_atoms"] = [makeAtom(name, v) for v in p.getElementsByTagName("unaffected")]
			self.packages[name].append(tmp)
		# TODO: services aren't really used yet
		self.services = self.affected.getElementsByTagName("service")
		return None

	def dump(self, outstream=sys.stdout, encoding="utf-8"):
		"""
		Dumps a plaintext representation of this GLSA to I{outfile} or
		B{stdout} if it is ommitted. You can specify an alternate
		I{encoding} if needed (default is utf-8).

		@type	outstream: File
		@param	outfile: Stream that should be used for writing
						 (defaults to sys.stdout)
		"""
		outstream = codecs.getwriter(encoding)(outstream)
		width = int(self.config["PRINTWIDTH"])
		outstream.write(center("GLSA %s: \n%s" % (self.nr, self.title), width)+"\n")
		outstream.write((width*"=")+"\n")
		outstream.write(wrap(self.synopsis, width, caption="Synopsis:         ")+"\n")
		outstream.write("Announced on:      %s\n" % self.announced)
		outstream.write("Last revised on:   %s : %02d\n\n" % (self.revised, self.count))
		if self.glsatype == "ebuild":
			for k in self.packages.keys():
				pkg = self.packages[k]
				for path in pkg:
					vul_vers = "".join(path["vul_vers"])
					unaff_vers = "".join(path["unaff_vers"])
					outstream.write("Affected package:  %s\n" % k)
					outstream.write("Affected archs:    ")
					if path["arch"] == "*":
						outstream.write("All\n")
					else:
						outstream.write("%s\n" % path["arch"])
					outstream.write("Vulnerable:        %s\n" % vul_vers)
					outstream.write("Unaffected:        %s\n\n" % unaff_vers)
		elif self.glsatype == "infrastructure":
			pass
		if len(self.bugs) > 0:
			outstream.write("\nRelated bugs:      ")
			outstream.write(", ".join(self.bugs))
			outstream.write("\n")
		if self.background:
			outstream.write("\n"+wrap(self.background, width, caption="Background:       "))
		outstream.write("\n"+wrap(self.description, width, caption="Description:      "))
		outstream.write("\n"+wrap(self.impact_text, width, caption="Impact:           "))
		outstream.write("\n"+wrap(self.workaround, width, caption="Workaround:       "))
		outstream.write("\n"+wrap(self.resolution, width, caption="Resolution:       "))
		myreferences = " ".join(r.replace(" ", SPACE_ESCAPE)+NEWLINE_ESCAPE for r in self.references)
		outstream.write("\n"+wrap(myreferences, width, caption="References:       "))
		outstream.write("\n")

	def isVulnerable(self):
		"""
		Tests if the system is affected by this GLSA by checking if any
		vulnerable package versions are installed. Also checks for affected
		architectures.

		@rtype:		Boolean
		@returns:	True if the system is affected, False if not
		"""
		rValue = False
		for k in self.packages.keys():
			pkg = self.packages[k]
			for path in pkg:
				if path["arch"] == "*" or self.config["ARCH"] in path["arch"].split():
					for v in path["vul_atoms"]:
						rValue = rValue \
							or (None != getMinUpgrade([v,], path["unaff_atoms"]))
		return rValue

	def isInjected(self):
		"""
		Looks if the GLSA ID is in the GLSA checkfile to check if this
		GLSA should be marked as applied.

		@rtype:		Boolean
		@returns:	True if the GLSA is in the inject file, False if not
		"""
		if not os.access(self.config["CHECKFILE"], os.R_OK):
			return False
		aList = portage.grabfile(self.config["CHECKFILE"])
		return (self.nr in aList)

	def inject(self):
		"""
		Puts the ID of this GLSA into the GLSA checkfile, so it won't
		show up on future checks. Should be called after a GLSA is
		applied or on explicit user request.

		@rtype:		None
		@returns:	None
		"""
		if not self.isInjected():
			checkfile = open(self.config["CHECKFILE"], "a+")
			checkfile.write(self.nr+"\n")
			checkfile.close()
		return None

	def getMergeList(self, least_change=True):
		"""
		Returns the list of package-versions that have to be merged to
		apply this GLSA properly. The versions are as low as possible
		while avoiding downgrades (see L{getMinUpgrade}).

		@type	least_change: Boolean
		@param	least_change: True if the smallest possible upgrade should be selected,
					False for an emerge-like algorithm
		@rtype:		List of Strings
		@return:	list of package-versions that have to be merged
		"""
		return list(set(update for (vuln, update) in self.getAffectionTable(least_change) if update))

	def getAffectionTable(self, least_change=True):
		"""
		Will initialize the self.systemAffection list of
		atoms installed on the system that are affected
		by this GLSA, and the atoms that are minimal upgrades.
		"""
		systemAffection = []
		for pkg in self.packages.keys():
			for path in self.packages[pkg]:
				update = getMinUpgrade(path["vul_atoms"], path["unaff_atoms"], minimize=least_change)
				if update:
					systemAffection.extend(update)
		return systemAffection
