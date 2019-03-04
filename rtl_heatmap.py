#!/usr/bin/env python2
import sys
import gzip
from datetime import datetime, timedelta
import time
import math
import os.path
import argparse
try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    from matplotlib.transforms import ScaledTranslation
    from matplotlib.colors import ListedColormap, hsv_to_rgb
except ImportError as i:
    print 'Error: you need **matplotlib** installed for this to run.'
    sys.exit(-1)

COLORMAPS = {
    'perceptual': ['viridis', 'plasma', 'inferno', 'magma', 'cividis', 'charolastra*'],
    'sequential': ['binary', 'gist_yarg', 'gist_gray', 'gray', 'bone', 'pink', 'spring', 'summer', 'autumn', 'winter', 'cool', 'Wistia', 'hot', 'afmhot', 'gist_heat', 'copper'],
    'diverging': ['PiYG', 'PRGn', 'BrBG', 'PuOr', 'RdGy', 'RdBu', 'RdYlBu', 'RdYlGn', 'Spectral', 'coolwarm', 'bwr', 'seismic'],
    'cyclic': ['twilight+', 'twilight_shifted+', 'hsv'],
    'qualitative': ['Pastel1', 'Pastel2', 'Paired', 'Accent', 'Dark2', 'Set1', 'Set2', 'Set3', 'tab10', 'tab20', 'tab20b', 'tab20c'],
    'misc': [ 'flag', 'prism', 'ocean', 'gist_earth', 'terrain', 'gist_stern', 'gnuplot', 'gnuplot2', 'CMRmap', 'cubehelix', 'brg', 'gist_rainbow', 'rainbow', 'jet', 'nipy_spectral', 'gist_ncar'],
}
MHz = 10**6
kHz = 10**3

def print_quiet(s, quiet):
    if not quiet:
        print s
def print_error(s):
    sys.stderr.write(s+'\n')
    sys.stderr.flush()

def read_data(f_name, quiet):
    print_quiet(':: reading file %s' % f_name, quiet)
    f_open = gzip.open if f_name.endswith('.gz') else open
    f = f_open(f_name, 'rb')
    lines = f.readlines()
    f.close()
    return lines

def sort_and_clean(L, start=None, end=None):
    indexes = {}
    if start or end:
        if start and end is None:
            flambda = lambda x: start < x
        elif start is None and end:
            flambda = lambda x: x < end
        elif start and end:
            flambda = lambda x: start < x < end

        for i,l in enumerate(L):
            fields = [f.strip() for f in l.split(',')]
            datetimefreq = '%sT%sF%s' % (fields[0], fields[1], fields[2])
            indexes[datetimefreq] = i
        si = filter(flambda, sorted(indexes.keys()))
        return [L[indexes[i]] for i in si]
    else:
        for i,l in enumerate(L):
            fields = [f.strip() for f in l.split(',')]
            datetimefreq = '%sT%sF%s' % (fields[0], fields[1], fields[2])
            indexes[datetimefreq] = i
        return [L[indexes[i]] for i in sorted(indexes.keys())]

def is_inside(b1, b2):
    return b1.xmax <= b2.xmax and b1.xmin >= b2.xmin and b1.ymax <= b2.ymax and b1.ymin >= b2.ymin

def charolastra_palette():
    def loop(n):
        t = n
        if n>1:
            t = 1
        elif n<0:
            t =  1-abs(n)
        return t

    p = []
    for i in range(1024):
        g = i / 1023.0
        c = hsv_to_rgb([loop(0.65-(g-0.08)), 1, loop(0.2+g)])
        p.append(c)
    return p

def floatify(zs):
    # nix errors with -inf, windows errors with -1.#J
    zf = []
    previous = 0  # awkward for single-column rows
    for z in zs:
        try:
            z = float(z)
        except ValueError:
            z = previous
        if math.isinf(z):
            z = previous
        if math.isnan(z):
            z = previous
        zf.append(z)
        previous = z
    return zf

def print_with_columns(L, columns, prefix=''):
    index = 0
    lines = []
    for i in range(int(round(float(len(L))/columns))):
        line = L[index:index+columns]
        line = line + ['']*(columns-len(line))
        lines.append(line)
        index += columns

    for i in range(columns):
        cmax = 0
        for j in range(len(lines)):
            cmax = max(cmax, len(lines[j][i]))
        for j in range(len(lines)):
            lines[j][i] = lines[j][i].ljust(cmax+2)

    for j in range(len(lines)):
        print prefix+''.join(lines[j])

def estimate_timelength(datetimes, span):
    # try to guess how much lines have been sampled for given span time
    start = datetime.strptime(datetimes[0], '%Y-%m-%dT%H:%M:%S')
    current = datetime.strptime(datetimes[0], '%Y-%m-%dT%H:%M:%S')
    index = 0
    while current < start+timedelta(seconds=span):
        index += 1
        current = datetime.strptime(datetimes[index], '%Y-%m-%dT%H:%M:%S')
    return index-1

def find_time_index(datetimes, multiple):
    # find index that matches the multiple in minute
    indexes = []
    done = []
    for i, dt in enumerate(datetimes):
        current = datetime.strptime(dt, '%Y-%m-%dT%H:%M:%S')
        if current.minute % multiple == 0:
            if dt[:17] not in done:
                done.append(dt[:17])
                indexes.append(i)
    return indexes

def find_freq_index(xmin, xmax, step, modulo):
    count = int(math.ceil((xmax-xmin)/step))
    freqs = [xmin]
    f = xmin
    for i in range(count):
        f = int(round(f+step))
        freqs.append(f)
    indexes = []
    done  = []
    for i,f in enumerate(freqs):
        fm = f / modulo
        if fm not in done and f % modulo < modulo/10:
            indexes.append(i)
            done.append(fm)
    return indexes

def remove_ticklabel(ax, axis, bbox):
    labels = getattr(ax, 'get_%sticklabels' % axis)()
    toberemoved = []
    for i,label in enumerate(labels):
        if not is_inside(label.get_window_extent(), bbox):
            toberemoved.append(i)
    ticks = list(getattr(ax, 'get_%sticks' % axis)())
    for i in reversed(toberemoved):
        del ticks[i]
    getattr(ax, 'set_%sticks' % axis)(ticks)

def plot_heatmap(lines, f_name, args):
    data = []
    tmp = []
    xmin = 10**10
    xmax = 0
    zmin = 100
    zmax = -100
    datetimes = []
    print_quiet(':: processing data', args.quiet)

    for i,line in enumerate(lines):
        fields = [f.strip() for f in line.split(',')]
        if i == 0:
            prev = '%sT%s' % (fields[0], fields[1])
            freq = '-1'
            step = float(fields[4])
        current = '%sT%s' % (fields[0], fields[1])
        if current == prev:
            xmax = max(xmax, int(fields[3]))
            xmin = min(xmin, int(fields[2]))
            if fields[2] == freq:
                tmp.extend(fields[7:])
            else:
                tmp.extend(fields[6:])
        else:
            tmp = floatify(tmp)
            zmax = max(zmax, max(tmp))
            zmin = min(zmin, min(tmp))
            data.append(tmp)
            tmp = fields[6:]
            datetimes.append(current)
        prev = current
        freq = fields[3]
    data.append(floatify(tmp)) # last line
    datetimes.append(current)
    print_quiet('Starting at %s and ending at %s\n  from %sHz to %sHz with values from %sdB to %sdB' % (datetimes[0], datetimes[-1], xmin, xmax, zmin, zmax), args.quiet)

    print_quiet(':: rendering', args.quiet)
    fig, ax = plt.subplots()

    def showfreq(tick, pos):
        #return '%gMHz' % ((xmin+float(tick)*float(step))/(1000*1000),)
        return '%dMHz' % int(round(((xmin+float(tick)*float(step))/(1000*1000))))

    start = time.mktime(time.strptime(datetimes[0], '%Y-%m-%dT%H:%M:%S'))
    end = time.mktime(time.strptime(datetimes[-1], '%Y-%m-%dT%H:%M:%S'))
    si = 11
    if end-start > 24*60*60:
        si = 0
    def showdatetime(tick, pos):
        try:
            dt = datetimes[int(tick)][si:16]
        except IndexError as i:
            dt = None
        return dt

    colormap = args.colormap
    if colormap != 'charolastra' and colormap not in plt.colormaps():
        print_error('Error: colormap "%s" not found; using charolastra palette' % colormap)
        colormap = 'charolastra'
    if colormap == 'charolastra':
        colormap = ListedColormap(charolastra_palette())

    if args.dbmin and args.dbmax:
        ax.imshow(data, cmap=colormap, aspect='equal', vmin=args.dbmin, vmax=args.dbmax)
    else:
        ax.imshow(data, cmap=colormap, aspect='equal')

    # show lines matching major ticks
    if args.xlines:
        ax.grid(True, axis='x', which='major', color='white', linewidth=0.5, linestyle='-.')
    if args.ylines:
        ax.grid(True, axis='y', which='major', color='white', linewidth=0.5, linestyle='-.')

    if xmax-xmin > 1000*MHz:
        txmajor = 100*MHz
    elif xmax-xmin > 100*MHz:
        txmajor = 10*MHz
    elif xmax-xmin > 10*MHz:
        txmajor = 1*MHz
    elif xmax-xmin > 1*MHz:
        txmajor = MHz
    else:
        txmajor = 10*kHz
    txminor = txmajor/10

    if args.yticks:
        tymajor = args.yticks
    else:
        length_min = (end-start)/60
        if length_min >= 60*24:
            tymajor = 60*2
        if length_min >= 60*6:
            tymajor = 60
        elif length_min >= 60*2:
            tymajor = 30
        else:
            tymajor = 15
    if tymajor >= 60*2:
        tyminor = tymajor/4
    elif tymajor >= 60:
        tyminor = 15
    elif tymajor >= 30:
        tyminor = 10
    elif tymajor >= 15:
        tyminor = 5

    # add the title
    if args.title:
        if args.inside:
            ax.text(0.5, 0.9, args.title, fontsize='x-large', color='white', horizontalalignment='center', verticalalignment='bottom', transform=ax.transAxes)
        else:
            ax.text(0.5, 1.01, args.title, fontsize='x-large', horizontalalignment='center', verticalalignment='bottom', transform=ax.transAxes)
    # redefine tick positions
    fi = find_freq_index(xmin, xmax, step, txminor)
    ax.set_xticks(fi[::10])
    ax.set_xticks(fi, minor=True)
    fi = find_time_index(datetimes, tyminor)
    ax.set_yticks(fi[::tymajor/tyminor])
    ax.set_yticks(fi, minor=True)
    # redefine tick labels
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(showfreq))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(showdatetime))

    # draw tick label inside plot in white
    if args.inside:
        ax.tick_params(axis='x', direction='in', which='both', color='white', pad=-15, zorder=1000)
        ax.tick_params(axis='y', direction='in', which='both', color='white', pad=-35, zorder=1000)
        for label in ax.get_xticklabels():
            label.set_color('white')
        for label in ax.get_yticklabels():
            label.set_color('white')
        # remove label outside of plot
        fig.canvas.draw()
        pos = ax.get_window_extent()
        remove_ticklabel(ax, 'x', pos)
        remove_ticklabel(ax, 'y', pos)

    if args.show:
        plt.show()
    else:
        if args.no_margin:
            size = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
            height = size.height
            width = size.width
            pad_inches = 0
        else:
            size = fig.get_size_inches()
            height = size[1]
            width = size[0]
            pad_inches = None
        height = height*fig.dpi*6
        width = width*fig.dpi*6
        dpi = 100
        fig.set_size_inches(float(width)/dpi, float(height)/dpi)
        fig.savefig(f_name, dpi=dpi, bbox_inches='tight', pad_inches=pad_inches)
        print_quiet(':: saved to %s' % f_name, args.quiet)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Yet another heatmap generator for rtl_power .csv file')
    parser.add_argument('--dbmin', help='Minimum value to consider for colormap normalization')
    parser.add_argument('--dbmax', help='Maximum value to consider for colormap normalization')
    parser.add_argument('-c', '--colormap', default='charolastra', help='Specify the colormap to use (all  to get a list of available colormaps)')
    parser.add_argument('-f', '--format', help='Format of the output image file')
    parser.add_argument('-i', '--input', help='Input csv filename')
    parser.add_argument('--inside', action='store_true', default=False, help='Draw tick label inside plot')
    parser.add_argument('--force', action='store_true', default=False, help='Force overwrite of existing output file')
    parser.add_argument('--no-margin', action='store_true', default=False, help="Don't draw any margin around the plot")
    parser.add_argument('-o', '--output', help='Explicit name for the output file')
    parser.add_argument('-q', '--quiet', action='store_true', default=False, help='no verbose output')
    parser.add_argument('-s', '--show', action='store_true', default=False, help='Show pyplot window instead of outputting an image')
    parser.add_argument('--start', help='Start time to use; everything before that is ignored; expected format YYY-mm-ddTHH[:MM[:SS]]')
    parser.add_argument('--end', help='End time to use; everything after that is ignored; expected format YYY-mm-ddTHH[:MM[:SS]]')
    parser.add_argument('--sort', action='store_true', default=False, help='Sort csv file data')
    parser.add_argument('--title', help='Add a title to the plot')
    parser.add_argument('--yticks', help='Define tick in the time axis, xxx[h|m]')
    parser.add_argument('--xlines', action='store_true', default=False, help='Show lines matching major xtick labels')
    parser.add_argument('--ylines', action='store_true', default=False, help='Show lines matching major ytick labels')
    args = parser.parse_args()

    if args.colormap == 'all':
        print 'Available colormaps are:'
        for k,v in COLORMAPS.items():
            print '  - %s:' % k
            print_with_columns(v, 6, prefix='    ')
            print
        sys.exit(1)

    if args.input is None:
        print_error('Error: -i/--input is required')
        sys.exit(-1)
    if not os.path.isfile(args.input):
        print_error('Error: there is no such file as %s' % args.input)
        sys.exit(-1)

    if args.output and args.format:
        ext = args.output[args.output.rindex('.')+1:]
        if ext.lower() != args.format.lower():
            print_error('Error: conflicting format and extension')
            sys.exit(-1)

    if (args.dbmin and not args.dbmax) or (args.dbmax and not args.dbmin):
        print_error('Error: please specify both --dbmin and --dbmax')
        sys.exit(-1)

    if args.yticks:
        if args.yticks.endswith('h'):
            args.yticks = int(args.yticks[:-1])*60
        elif args.yticks.endswith('m'):
            args.yticks = int(args.yticks[:-1])
        else:
            args.yticks = int(args.yticks)

    lines = read_data(args.input, args.quiet)
    if args.sort or args.start or args.end:
        # force also a sort if using either --start or --end
        lines = sort_and_clean(lines, start=args.start, end=args.end)

    if not args.output:
        output = args.input
        indx = output.rindex('.')
        ext = output[indx:]
        if ext.lower() == '.gz':
            output = output[:indx]
            indx = output.rindex('.')
            ext = output[indx:]
        if ext.lower() == '.csv':
            output = output[:indx]
        if not args.format:
            args.format = 'png'
        output = '%s.%s' % (output, args.format.lower())
    else:
        output = args.output
    if os.path.isfile(output) and not args.force:
        print_error('Abort: file %s already exits. Use --force to overwrite.' % output)
        sys.exit(-1)

    plot_heatmap(lines, output, args)
