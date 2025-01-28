from glob import glob
import sys
import re

# Plan:
# 1. Take list of packages that we want to build (from ci python file)
# 2. Parse control file of each package, store source pkg and pkg info
# 3. For each package, remove any deps that aren't provided by our general deps
#    (assume they are debian provided)
# 4. For each package, see if we can build it with current satisfied deps - if
#    we can, add what it provides to our current deps
# 5. See if we don't get stuck
# 6. ???
# 7. Profit
#
# This can be tested by manually loading 5-10 packages first, and seeing how it
# works with those.

subsect_start = re.compile(r'^([A-Za-z\-]+):')



def strip_version(s):
    s = s.split('(')[0].strip()
    s = s.split('[')[0].strip()
    s = s.split('<')[0].strip()
    s = s.split(':')[0].strip()
    return s


def parse_field(name, field):
    if name in ('Description', 'Maintainer'):
        return ([field])

    field_parts = []

    parts = field.split(',')
    for part in parts:
        part = part.strip()
        if '|' in part:
            or_parts = []
            for or_part in part.split('|'):
                or_parts.append(strip_version(or_part))
            field_parts.append([or_parts])
        else:
            first_part = strip_version(part)
            if first_part:
                field_parts.append([first_part])

    return field_parts


def parse_section(section):
    lines = section.split('\n')

    line_subsect = {}

    subsect = None
    for line in lines:
        # Ignore empty lines (extra newlines)
        if not line.strip():
            continue

        if line.startswith('#'):
            continue

        starter = subsect_start.match(line)
        if starter:
            subsect = starter.groups()[0]
            if subsect not in line_subsect:
                line_subsect[subsect] = ''

            line_subsect[subsect] += line[len(subsect)+1:].strip()
        else:
            if subsect is None:
                raise ValueError('Line has no subsection')
            line_subsect[subsect] += line.strip()

    return line_subsect


def parse_pkg(fn, honour_src=True):
    #print('Parsing:', fn)
    with open(fn) as fp:
        contents = fp.read()

    package_source = None
    package_pkgs = []

    sections = contents.split('\n\n')
    for section in sections:
        parsed_section = parse_section(section)
        parsed_section.pop('Description', None)

        keys = dict([(key, parse_field(key, value)) for (key, value) in parsed_section.items()])
        if parsed_section.get('Source') and honour_src:
            package_source = keys
        elif parsed_section.get('Package'):
            package_pkgs += [keys]

    return package_source, package_pkgs


def parse_packages(control_files, parse_packages_file=False):
    # What does a parsed package look like?
    # * (source) package name
    # * build depends
    # * packages provided once built

    parsed_packages = []
    in_pkgs = [parse_pkg(x, honour_src=not parse_packages_file) for x in control_files]
    for (src_pkg, pkg_pkg) in in_pkgs:
        if not parse_packages_file:
            pkg_name = src_pkg['Source']
            pkg_build_dep = src_pkg.get('Build-Depends', [])
        else:
            pkg_name = 'nan'
            pkg_build_dep = []

        pkg_provides = []

        for pp in pkg_pkg:
            pkg_provides += pp.get('Package') + pp.get('Provides', []) + pp.get('Replaces', [])

        # XXX: Get rid of this later
        pkg_build_dep = flat(pkg_build_dep)
        pkg_provides = flat(pkg_provides)

        parsed_packages.append({'name': pkg_name[0], 'build_dep': pkg_build_dep,
                                'provides': pkg_provides})

    return parsed_packages


def flat(l):
    return [x for y in l for x in y]


def remove_pkg_nonexistent(parsed_packages, world_provided):
    removed_pkgs = set()
    for pkg in parsed_packages:
        new_build_dep = []
        for build_dep in pkg['build_dep']:
            if isinstance(build_dep, list):
                new_bdp = []
                for bdp in build_dep:
                    if bdp in world_provided:
                        new_bdp += [bdp]
                    else:
                        removed_pkgs.add(bdp)
                if len(new_bdp):
                    new_build_dep += new_bdp
            else:
                if build_dep in world_provided:
                    new_build_dep += [build_dep]
                else:
                    removed_pkgs.add(build_dep)

        #print('OLD:', pkg['build_dep'], 'NEW:', new_build_dep)
        pkg['build_dep'] = new_build_dep

    return removed_pkgs


def package_build_order(parsed_packages, inject_deps):
    max_tries = len(parsed_packages)

    print('Total:', len(parsed_packages))
    cur_provided = list(inject_deps)
    pkg_order = []
    for tries in range(10):
        #print('len:', len(parsed_packages))
        if not len(parsed_packages):
            break

        for pkg in parsed_packages:
            #print('trying:', pkg['name'], 'with deps', pkg['build_dep'])
            satisfied = True

            for dep in pkg['build_dep']:
                #print('checking:', dep)
                if isinstance(dep, list):
                    satisfied = any([x in cur_provided for x in dep])
                else:
                    satisfied = dep in cur_provided

                if not satisfied:
                    break

            #print(pkg['name'], 'satisfied:', satisfied)

            if not satisfied:
                continue

            #print('Adding:', pkg['name'])

            cur_provided.extend(pkg['provides'])
            pkg_order.append(pkg['name'][0])
            parsed_packages.remove(pkg)

    if len(parsed_packages):
        print(len(parsed_packages))
        #print('Remaining:', [pkg['name'] for pkg in parsed_packages])
        raise Exception('Failed to resolve')

    return pkg_order



if __name__ == '__main__':
    from jobs import jobs, injected_deps
    debian_control_files = sys.argv[1:]
    control_files = ['../%s/debian/control' % name for name in jobs]
    #control_files = glob(sys.argv[1])

    deb_parsed_packages = parse_packages(debian_control_files,
                                         parse_packages_file=True)
    deb_world_provided = flat(pp['provides'] for pp in deb_parsed_packages)

    parsed_packages = parse_packages(control_files)

    world_provided = flat(pp['provides'] for pp in parsed_packages)

    removed = remove_pkg_nonexistent(parsed_packages, world_provided + deb_world_provided)
    #print('removed:', removed)

    #print(parsed_packages)
    pkg_order = package_build_order(parsed_packages, injected_deps + deb_world_provided)
    print('Order:', pkg_order)
