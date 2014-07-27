#!/usr/bin/env python

# HQ XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# HQ X
# HQ X   quippy: Python interface to QUIP atomistic simulation library
# HQ X
# HQ X   Copyright James Kermode 2010
# HQ X
# HQ X   These portions of the source code are released under the GNU General
# HQ X   Public License, version 2, http://www.gnu.org/copyleft/gpl.html
# HQ X
# HQ X   If you would like to license the source code under different terms,
# HQ X   please contact James Kermode, james.kermode@gmail.com
# HQ X
# HQ X   When using this software, please cite the following reference:
# HQ X
# HQ X   http://www.jrkermode.co.uk/quippy
# HQ X
# HQ XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

import sys
import optparse

import numpy as np

from ase.atoms import Atoms as AseAtoms
from ase.data import atomic_masses
from ase.db import connect
from ase.db.cli import plural
from ase.db.core import float_to_time_string, now

from quippy.io import dict2atoms, AtomsWriter

def cut(txt, length):
    if length is None or length == 0:
        return txt
    if len(txt) <= length:
        return txt
    return txt[:length - 3] + '...'

class Formatter(object):
    """
    Modified version of old ase.db.cli.Formatter class
    """
    def __init__(self, cols, sort):
        self.sort = sort
        
        self.columns = ['id', 'age', 'user', 'formula', 'calc',
                        'energy', 'fmax', 'pbc', 'size', 'keywords',
                        'charge', 'mass', 'fixed', 'smax', 'magmom', 'cell']
        
        if cols is not None and len(cols) > 0:
            if cols[0] == '+':
                cols = cols[1:]
            elif cols[0] != '-':
                self.columns = []
            for col in cols.split(','):
                if col[0] == '-':
                    self.columns.remove(col[1:])
                else:
                    self.columns.append(col.lstrip('+'))
        
        self.funcs = []
        for col in self.columns:
            f = getattr(self, col, None)
            if f is None:
                f = self.keyval_factory(col)
            self.funcs.append(f)

    def id(self, d):
        return d.id
    
    def age(self, d):
        return float_to_time_string(now() - d.ctime)

    def user(self, d):
        return d.user
    
    def formula(self, d):
        return AseAtoms(d.numbers).get_chemical_formula()

    def energy(self, d):
        return d.energy

    def size(self, d):
        dims = d.pbc.sum()
        if dims == 0:
            return ''
        if dims == 1:
            return np.linalg.norm(d.cell[d.pbc][0])
        if dims == 2:
            return np.linalg.norm(np.cross(*d.cell[d.pbc]))
        return abs(np.linalg.det(d.cell))

    def cell(self, d):
        if np.all(np.diag(np.diag(d.cell)) == d.cell):
            return cut('diag([%.1f, %.1f, %.1f])' % tuple(np.diag(d.cell)), self.opts.cut)
        else:
            return cut('[[%.1f, %.1f, %.1f], [%.1f, %.1f, %.1f], [%.1f, %.1f, %.1f]]' % tuple(d.cell.flat), self.opts.cut)

    def pbc(self, d):
        a, b, c = d.pbc
        return '%d%d%d' % tuple(d.pbc)

    def calc(self, d):
        return d.calculator

    def fmax(self, d):
        c = d.constraints
        if c is None:
            f = d.forces
        if len(c) > 1:
            f = d.forces
        c = c[0]
        if 'mask' in c:
            f = d.forces[np.invert(c['mask'])]
        else:
            f = d.forces
        return (f**2).sum(axis=1).max()**0.5

    def keywords(self, d):
        return cut(','.join(d.keywords), self.opts.cut)

    def keyvals(self, d):
        return cut(','.join(['%s=%s' % (key, cut(str(value), 8))
                             for key, value in d.key_value_pairs.items()]), 40)

    def data(self, d):
        return cut(','.join(d.data.keys()), self.opts.cut)

    def charge(self, d):
        return d.charge

    def mass(self, d):
        if 'masses' in d:
            return d.masses.sum()
        return atomic_masses[d.numbers].sum()

    def fixed(self, d):
        c = d.constraints
        if c is None:
            return ''
        if len(c) > 1:
            return '?'
        c = c[0]
        if 'mask' in c:
            return sum(c['mask'])
        return len(c['indices'])

    def smax(self, d):
        return (d.stress**2).max()**0.5

    def magmom(self, d):
        return d.magmom or ''

    def keyval_factory(self, key):
        def keyval_func(d):
            value = d.key_value_pairs.get(key, '(none)')
            return str(value)
        return keyval_func

    def format(self, dcts, opts):
        self.opts = opts
        columns = self.columns
        if opts.uniq:
            columns += ['repeat']
        if opts.wiki_table:
            columns = ['*%s*' % col for col in columns]
        table = [columns]
        widths = [0 for col in columns]
        signs = [1 for col in columns]  # left or right adjust
        ids = []
        fd = sys.stdout
        for dct in dcts:
            row = []
            for i, f in enumerate(self.funcs):
                try:
                    s = f(dct)
                except AttributeError:
                    s = ''
                else:
                    if isinstance(s, int):
                        s = '%d' % s
                    elif isinstance(s, float):
                        s = '%.3f' % s
                    else:
                        signs[i] = -1
                    if len(s) > widths[i]:
                        widths[i] = len(s)
                row.append(s)
            table.append(row)
            ids.append(dct.id)

        if self.sort:
            headline = table.pop(0)
            n = self.columns.index(self.sort)
            table.sort(key=lambda row: row[n])
            table.insert(0, headline)

        if opts.uniq:
            uniq_table = [table.pop(0)] # header rows
            first_row = table.pop(0)
            count = 1
            for row in table:
                if row == first_row:
                    count += 1
                else:
                    uniq_table.append(first_row + [count])
                    widths[-1] = max(widths[-1], len(str(count)))
                    first_row = row
                    count = 1

            uniq_table.append(first_row + [count])
            widths[-1] = max(widths[-1], len(str(count)))

            table = uniq_table

        widths = [w and max(w, len(col))
                  for w, col in zip(widths, columns)]

        columns = [ col for w, col in zip(widths, table[0]) if w > 0]

        if not opts.list_columns:
            for row in table:
                line = '|'.join('%*s' % (w * sign, s)
                                  for w, sign, s in zip(widths, signs, row)
                                  if w > 0)
                if opts.wiki_table:
                    line = '|' + line + '|'
                fd.write(line)
                fd.write('\n')
        return (ids, columns)
    

def run(opts, args, verbosity):
    args = args[:]
    con = connect(args.pop(0))
    if args:
        if len(args) == 1 and args[0].isdigit():
            expressions = int(args[0])
        else:
            expressions = ','.join(args)
    else:
        expressions = []

    if opts.count or opts.uniq:
        opts.limit = 0

    rows = con.select(expressions, verbosity=verbosity, limit=opts.limit)

    if opts.count:
        n = 0
        for row in rows:
            n += 1
        print('%s' % plural(n, 'row'))
        return

    dcts = list(rows)

    if len(dcts) > 0:
        if opts.include_all or opts.list_columns:
            keys = []
            for dct in dcts:
                if hasattr(dct, 'key_value_pairs'):
                    for key in dct.key_value_pairs.keys():
                        if key not in keys:
                            keys.append(key)
            opts.columns = ','.join(['+'+key for key in keys])

        f = Formatter(opts.columns, opts.sort)
        if verbosity >= 1:
            ids, columns = f.format(dcts, opts)
        if verbosity > 1 or opts.list_columns:
            for col in columns:
                if not opts.list_columns:
                    print 'COLUMN',
                print col
            if opts.list_columns:
                return

        if opts.extract is not None:
            if '%' not in opts.extract:
                writer = AtomsWriter(opts.extract)
            for i, dct in enumerate(dcts):
                if '%' in opts.extract:
                    filename = opts.extract % i
                    writer = AtomsWriter(filename)
                at = dict2atoms(dct)
                if verbosity > 1:
                    print 'Writing config %d %r to %r' % (i, at, writer)
                writer.write(at)

examples = [
    'List all columns in database, one per line, then exit',
    '  db-dump.py Si_GAP.db -C',
    '',
    'List columns held for rows with diamond-structure config_type',
    '  db-dump.py Si_GAP.db config_type=dia -C',
    '',
    'Number of rows with DFT total energy below -2e4 eV',
    '  db-dump.py Si_GAP.db \'dft_energy<-2e4\' -n',
    '',
    'Table of all rows and columns (up to default --limit=500 rows)',
    '  db-dump.py Si_GAP.db -a',
    '',
    'Table of all columns for rows matching expression',
    '  db-dump.py Si_GAP.db config_type=bt -a',
    '',
    'Table of specific columns for rows matching expression',
    '  db-dump.py Si_GAP.db config_type=bt -c id,formula,calc,dft_energy,config_type',
    '',
    'Specific columns, in sorted order. Duplicate rows suppressed with -u/--uniq',
    '  db-dump.py Si_GAP.db -c user,formula,calc,config_type -s config_type -u',
    '',
    'Print all information held about any configs less than one hour old',
    '  db-dump.py Si_GAP.db \'age<1h\' -a',
    '',
    'Extract rows with two or fewer atoms to single .xyz file',
    '  db-dump.py Si_GAP.db \'natoms<=2\' -x primitive.xyz',
    '',
    'Extract rows with more than 100 Si atoms to a series of .cell files',
    '  db-dump.py Si_GAP.db \'Si>100\' -x big-%03d.cell'
    ]

class OptionParser(optparse.OptionParser):
    def format_epilog(self, formatter):
        return self.epilog
                
parser = OptionParser(
    usage='Usage: %prog db-name [selection] [options]',
    description='''Print a formatted table of data from an ase.db database.
Optionally extracts matching configs and write them to files in any format
supported by quippy.''',
    epilog='Examples: \n\n' + '\n'.join(examples) + '\n\n')

add = parser.add_option
add('-v', '--verbose', action='store_true', default=False)
add('-q', '--quiet', action='store_true', default=False)
add('-n', '--count', action='store_true',
    help='Count number of selected rows. Implies --limit=0.')
add('-C', '--list-columns', action='store_true', default=False,
    help='Print list of available columns and exit.')
add('-c', '--columns', metavar='col1,col2,...',
    help='Specify columns to show.  Precede the column specification ' +
    'with a "+" in order to add columns to the default set of columns.  ' +
    'Precede by a "-" to remove columns.')
add('-a', '--include-all', action='store_true', default=False,
    help='Include columns for all key/value pairs in database.')
add('-s', '--sort', metavar='column',
    help='Sort rows using column.  Default is to sort after ID.')
add('-u', '--uniq', action='store_true',
    help='Suppress printing of duplicate rows. Implies --limit=0.')
add('-x', '--extract', metavar='filename',
    help='''Extract matching configs and save to file(s). Use a filename containing a
"%" expression for multiple files labelled by an index starting from 0,
e.g. "file-%03d.xyz".''')
add('--limit', type=int, default=500, metavar='N',
    help='Show only first N rows (default is 500 rows).  Use --limit=0 ' +
    'to show all.')
add('-w', '--wiki-table', action='store_true',
    help='Format output as a Wiki table')
add('--cut', action='store', type=int, default=30,
    help='Truncate columns after CUT characters. Default 30. Use 0 for no limit')

opts, args = parser.parse_args()
verbosity = 1 - opts.quiet + opts.verbose

try: 
    run(opts, args, verbosity)
except Exception as x:
    if verbosity < 2:
        print('{0}: {1}'.format(x.__class__.__name__, x.message))
        sys.exit(1)
    else:
        raise


