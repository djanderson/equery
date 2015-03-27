# equery
Major rewrite/refactor of Gentoo Linux's equery tool (circa 2009)

Between 2008 and 2009, I rewrote or refactored a large part of Gentoo Linux's equery tool and related documentation. In 2009, it was merged into Gentoo's SVN and released as gentoolkit-0.3.0. This repo and the following text lived at http://genscripts.googlecode.com.

Following is the old Google Code wiki page:

A repository of scripts for Gentoo Linux
----------------------------------------

To checkout the latest gentoolkit tree into a directory named "gentoolkit" in the current directory, do:
```
svn co http://genscripts.googlecode.com/svn/trunk/gentoolkit
```
And to start using it immediately in the current terminal:
```
export PYTHONPATH="$(pwd)/gentoolkit/pym:${PYTHONPATH}"
export PATH="$(pwd)/gentoolkit/bin:${PATH}"
```

News
----
 Nov 18, 2009
  Though *gentoolkit-0.3.0_rc7* is the most recent version available in the tree, there have been some very important changes due to come out in *rc8*, which will hopefully be the last release candidate.
  * *equery*'s man page has been completely rewritten, though there are still a number of updates to do.
  * *equery meta*'s metadata handling has been extracted into the main *gentoolkit* library as the *MetaData* class, a convenient python interface to Gentoo's metadata.xml file for other scripts' convenience.
  * With this was added an increase in functionality that allows us to handle *epkginfo*'s use cases completely. *epkginfo* now calls *equery meta*.
  * In a similar vain, _dol-sen@freenode_ prodded and helped with a complete rewrite of the dependency handling stuff in *equery*. This task is about 80 percent finished, and we've seen an awesome increase in usability for external consumers, but more importantly, speed! Check this out:
```
$ # rc7, hot cache, direct dependencies:
$ time equery depends portage |wc -l
4

real	0m8.230s
user	0m7.481s
sys	0m0.319s

$ # rc7, hot cache, indirect dependencies:
$ time equery depends -D portage |wc -l
4791

real	2m30.264s
user	2m8.664s
sys	0m5.279s

$ # HEAD, hot cache, direct dependencies:
$ time equery -q depends portage |wc -l
4

real	0m2.381s
user	0m2.115s
sys	0m0.145s

$ # HEAD, hot cache, indirect dependencies:
$ time equery -q depends -D portage |wc -l
4708

real	0m16.034s
user	0m15.147s
sys	0m0.147s

$ # (The discrepancy in total indirect packages is not a bug.
$ # If you're interested, the specifics of that can be found in the following link):
```
    * http://code.google.com/p/genscripts/source/detail?r=57
  * A longstanding bug where *equery list* and *hasuse* reported mask status in a confusing (usually incorrect) way has been fixed.
  * *equery list* has an useful new feature: `-m, --mask-reason`:
```
$ equery list -p --mask-reason '=sys-apps/portage-2.2_rc50'
 * Searching for portage in =sys-apps ...
[-P-] [M~] sys-apps/portage-2.2_rc50 (0)
 * Masked by 'package.mask, ~x86 keyword'
 * /usr/portage/profiles/package.mask:
 * Zac Medico <zmedico@gentoo.org> (05 Jan 2009)
 * Portage 2.2 is masked due to known bugs in the
 * package sets and preserve-libs features.
```
  * Tons of other bug fixes and speed improvements... thanks for helping bugtest.
 May 11, 2009
   gentoolkit-0.3.0_rc5 with all my changes is in the Portage tree. Check it out and help us bugtest!
 April 19, 2009
   Super happy with this: I just pushed out rc10, and it's a good one. The really hacky find_matches and friends from helpers2 is dead and gone. I replaced it with a new function called do_lookup. do_lookup differs from find_matches and previous version of gentoolkit by doing exact name matching by default (so no more -e, --exact-name options). To replicate the previous behavior, I've implemented package name globbing. This allows consistant and super flexible package name matching in all equery modules.
   I really wanted to avoid changing equery's behavior this way, but it just needed to happen for two reasons. One: some modules used fuzzy name matching by default, with the option to do --exact-name matching, while others used exact-name matching by default, with no option to do fuzzy matching. That's confusing. Two: there was some really nasty magic in the way gentoolkit did fuzzy matching before. Take, for example:
```
# Previous gentoolkits:
$ equery l sys-apps/orta
[ Searching for orta in sys-apps... ]
 * installed packages:
[I--] [ ~] sys-apps/portage-2.2_rc30 (0)
```
   `sys-apps/orta` matches sys-apps/portage? hmm... with the new globbing support, things look a bit more familiar:
```
# From rc 10
$ equery l 'sys-apps/*orta*'
 * Searching for *orta* in sys-apps ...
 * installed packages:
[I--] [ ~] sys-apps/portage-2.2_rc30 (0)
```
   Globbings works in categories and version, too (note how when you use the --category switch, globs are expanded before being printed to the screen so you can see where equery is looking):
```
$ equery l '*' --category '*lang*'
 * Searching for * in dev-lang ...
 * installed packages:
[I--] [ ~] dev-lang/dmd-bin-2.008-r1 (0)
[I--] [  ] dev-lang/mono-2.0.1-r1 (0)
[I--] [ -] dev-lang/nasm-2.05.01 (0)
[I--] [  ] dev-lang/perl-5.8.8-r5 (0)
[I--] [ ~] dev-lang/python-2.6.2 (2.6)
[I--] [  ] dev-lang/swig-1.3.36 (0)
[I--] [ -] dev-lang/yasm-0.7.1 (0)
```
   There's probably a few other cool things you can do with this, and I'm sure I've introduced a few little bugs, as well, so thanks in advance for you help testing.
   I got news from FuzzyRay (who's my contact at Gentoo for this work) that this should be moved into the tree any time now. The only thing left on my "todo" besides nitpicky stuff is to work out a way for all gentoolkit scripts to share a single version.
 April 17, 2009
   Just pushed through release candidate 9, including all the changes  mentioned below, with a ton more bug fixes. The big news for this RC is that `changes` can now make use of the new features of Package to allow really flexible version searching. The "examples" sections of `changes -h` gives an overview of the new capabilities:
```
$ equery c -h
Display the  Gentoo ChangeLog entry for the latest installable version of a
given package

Usage: changes [options] pkgspec

examples
 c portage                                # show latest visible version's entry
 c portage --full --limit=3               # show 3 latest entries
 c '=sys-apps/portage-2.1.6*'             # use atom syntax
 c portage --from=2.2_rc20 --to=2.2_rc30  # use version ranges

options
 -h, --help              display this help message
 -l, --latest            display only the latest ChangeLog entry
 -f, --full              display the full ChangeLog
     --limit=NUM         limit the number of entries displayed (with --full)
     --from=VER          set which version to display from
     --to=VER            set which version to display to
```
   The other big news on the code side of things is that all modules inside the "equery" directory pass pylint with a 10/10 score :)
 March 29, 2009
   No new release yet, but a really nice commit just now dealing with gentoolkit.packages. The commit message gives a brief overview: ```"Adding tons of useful backwards-compatible features to the package.Package class. Adds 'category, cp, name, version, revision, fullversion, and cpv' as attributes of a Package instance, adds a __repr__ method which displays the cpv among other useful info, adds a __cmp__ method to allow for sorting sequences of Package objects with the builtin sort, adds and __eq__ and __ne__ method which detects the equality of either another Package object or a string (by using the new __hash__ method. This has the added benefit of letting us do fast membership testing on a set of Package objects.), adds a __str__ method which displays the cpv string, and a few other cleanups."``` These are not original ideas of course. The majority of the ideas came from `pkgcore's pkgcore.ebuild.atom.atom`, `pkgcore.ebuild.cpv.CPV`, and `portage._emerge.Package`. Within the next week I'm going to try and move the codebase back to using the Package format wherever possible. Next big goal is to steal the "intersects" method from pkgcore. We'll see how painful that is.

 March 3, 2009
  Well within a little more than 10 days I've pushed 8 release candidates into the genscripts overlay. Today, with the release of rc8, I finally got the chance to go through each equery module and exercise each option. I'm pretty confident that I've squashed at least the large majority of regressions. Release candidate 8 should be getting pretty solid, so I will start to work with the tools-portage herd devs to get this thing in the tree ASAP; probably masked for testing at first, and while I rewrite the necessary documentation. Until then, anyone who finds any problems, feel free to click of the "Issues" tab above and leave me a note.

 Feb 19, 2009
  I've been working quite hard to get a cleaned up equery out the door. Some new features in the gentoolkit-0.2.5 branch are:
  * new equery menu options:
    * equery changes - Gentoo changelog entry viewer
    * equery meta - similar in a way to epkginfo, but more focuses on displaying all the information available in metadata.xml
  * cleaned up menus and UI in equery
  * rewrite of most gentoolkit.helpers functions as helpers2.py (some huge speed improvements)
  * complete internal restructuring and code review of equery
  * simplified "distutils" distribution method; gentoolkit, equery, and glsa modules are now installed directly into python/site-packages.
  * many others. I will write up a more detailed introduction to the changes in equery and post it to gentoo forums as well as in NEWS in the source tarball.

 Nov 24, 2008
  emeta-2.0.5 is out, fixed Issue 1. Thanks to Daniel Pielmeier for reporting. Also new in this release is the option: _`emeta -c|--current`_ It might be useful for ebuild authors without a custom overlay or for people who want to read metadata in an overlay when *emeta* is defaulting to a version in the main tree.