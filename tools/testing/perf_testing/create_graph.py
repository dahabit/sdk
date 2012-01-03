#!/usr/bin/python

# Copyright (c) 2011, the Dart project authors.  Please see the AUTHORS file
# for details. All rights reserved. Use of this source code is governed by a
# BSD-style license that can be found in the LICENSE file.

import datetime
import math
try:
  from matplotlib.font_manager import FontProperties
  import matplotlib.pyplot as plt
except ImportError:
  print 'Warning: no matplotlib. ' + \
      'Please ignore if you are running buildbot smoketests.'
import optparse
import os
from os.path import dirname, abspath
import platform
import shutil
import subprocess
import time
import traceback
import sys

TOOLS_PATH = os.path.join(dirname(dirname(dirname(abspath(__file__)))))
sys.path.append(TOOLS_PATH)
import utils

"""This script runs to track performance and correctness progress of 
different svn revisions. It tests to see if there a newer version of the code on
the server, and will sync and run the performance tests if so."""

DART_INSTALL_LOCATION = os.path.join(dirname(abspath(__file__)),
    '..', '..', '..')
V8_MEAN = 'V8 Mean'
FROG_MEAN = 'frog Mean'
COMMAND_LINE = 'commandline'
V8 = 'v8'
FROG = 'frog'
V8_AND_FROG = [V8, FROG]
CORRECTNESS = 'Percent passing'
COLORS = ['blue', 'green', 'red', 'cyan', 'magenta', 'black']
GRAPH_OUT_DIR = 'graphs'
SLEEP_TIME = 200
PERFBOT_MODE = False
VERBOSE = False
HAS_SHELL = False
if platform.system() == 'Windows':
  # On Windows, shell must be true to get the correct environment variables.
  HAS_SHELL = True

"""First, some utility methods."""

def run_cmd(cmd_list, outfile=None, append=False):
  """Run the specified command and print out any output to stdout.
  Args:
    cmd_list a list of strings that make up the command to run
    outfile a string indicating the name of the file that we should write stdout
       to 
    append True if we want to append to the file instead of overwriting it"""
  if VERBOSE:
    print ' '.join(cmd_list)
  out = subprocess.PIPE
  if outfile:
    mode = 'w'
    if append:
      mode = 'a'
    out = open(outfile, mode)
  p = subprocess.Popen(cmd_list, stdout = out, stderr = subprocess.PIPE,
      shell=HAS_SHELL)
  output, not_used = p.communicate();
  if output:
    print output
  return output

def time_cmd(cmd):
  """Determine the amount of (real) time it takes to execute a given command."""
  start = time.time()
  run_cmd(cmd)
  return time.time() - start

def sync_and_build(failed_once=False):
  """Make sure we have the latest version of of the repo, and build it. We
  begin and end standing in DART_INSTALL_LOCATION.
  Args:
    failed_once True if we have attempted to build this once before, and we've
      failed, indicating the build is broken.
  Returns:
    err_code = 1 if there was a problem building two times in a row."""
  os.chdir(DART_INSTALL_LOCATION)
  #Revert our newly built minfrog to prevent conflicts when we update
  run_cmd(['svn', 'revert',  os.path.join(os.getcwd(), 'frog', 'minfrog')])

  run_cmd(['gclient', 'sync'])
  # TODO(efortuna): building the sdk locally is a band-aid until all build
  # platform SDKs are hosted in Google storage. Pull from https://sandbox.
  # google.com/storage/?arg=dart-dump-render-tree#dart-dump-render-tree%2Fsdk
  # eventually.
  # TODO(efortuna): Currently always building ia32 architecture because we don't
  # have test statistics for what's passing on x64. Eliminate arch specification
  # when we have tests running on x64, too.
  lines = run_cmd([os.path.join('.', 'tools', 'build.py'), '-m', 'release',
    '--arch=ia32', 'create_sdk'])
  
  for line in lines:
    if 'BUILD FAILED' in lines:
      if failed_once:
        # Someone checked in a broken build! Just stop trying to make it work
        # and wait to try again.
        print 'Broken Build'
        return 1
      #Remove the output directory and attempt to build again. If it still
      #fails, abort, and try again in a little bit.
      shutil.rmtree(os.path.join(os.getcwd(), 
          utils.GetBuildRoot(utils.GuessOS(), 'release', 'ia32')))
      sync_and_build(True)
  return 0

def ensure_output_directory(dir_name):
  """Test that the listed directory name exists, and if not, create one for
  our output to be placed.
  Args:
    dir_name the directory we will create if it does not exist."""
  dir_path = os.path.join(DART_INSTALL_LOCATION, 'tools', 'testing',
      'perf_testing', dir_name)
  if not os.path.exists(dir_path):
    os.mkdir(dir_path)
    print 'Creating output directory ', dir_path

def has_new_code():
  """Tests if there are any newer versions of files on the server."""
  os.chdir(DART_INSTALL_LOCATION)    
  results = run_cmd(['svn', 'st', '-u'])
  for line in results:
    if '*' in line:
      return True
  return False

def get_browsers():
  if not PERFBOT_MODE:
    # Only Firefox (and Chrome, but we have Dump Render Tree) works in Linux
    return ['ff']
  browsers = ['ff', 'chrome', 'safari']
  if platform.system() == 'Windows':
    browsers += ['ie']
  return browsers

def get_versions():
  if not PERFBOT_MODE:
    return [FROG]
  else:
    return V8_AND_FROG

def get_benchmarks():
  if not PERFBOT_MODE:
    return ['Smoketest']
  else:
    return ['Mandelbrot', 'DeltaBlue', 'Richards', 'NBody', 'BinaryTrees',
    'Fannkuch', 'Meteor', 'BubbleSort', 'Fibonacci', 'Loop', 'Permute',
    'Queens', 'QuickSort', 'Recurse', 'Sieve', 'Sum', 'Tak', 'Takl', 'Towers',
    'TreeSort']

def upload_to_app_engine():
  """Upload our results to our appengine server."""
  # TODO(efortuna): This is the most basic way to get the data up 
  # for others to view. Revisit this once we're serving nicer graphs (Google
  # Chart Tools) and from multiple perfbots and once we're in a position to
  # organize the data in a useful manner(!!).
  os.chdir(os.path.join(DART_INSTALL_LOCATION, 'tools', 'testing',
      'perf_testing'))
  shutil.rmtree(os.path.join('appengine', 'static', 'graphs'), 
      ignore_errors=True)
  shutil.copytree('graphs', os.path.join('appengine', 'static', 'graphs'))
  shutil.copyfile('index.html', os.path.join('appengine', 'static', 
      'index.html'))
  run_cmd(['../../../third_party/appengine-python/1.5.4/appcfg.py', 'update', 
      'appengine/'])

class TestRunner(object):
  """The base clas to provide shared code for different tests we will run and
  graph."""

  def __init__(self, result_folder_name, platform_list, v8_and_or_frog_list, 
      values_list):
    """Args:
         result_folder_name the name of the folder where a tracefile of
         performance results will be stored.
         platform_list a list containing the platform(s) that our data has been
            run on. (command line, firefox, chrome, etc)
         v8_and_or_frog_list a list specifying whether we hold data about Frog
            generated code, plain JS code (v8), or a combination of both.
         values_list a list containing the type of data we will be graphing
            (benchmarks, percentage passing, etc)"""
    self.result_folder_name = result_folder_name
    # cur_time is used as a timestamp of when this performance test was run.
    self.cur_time = str(time.mktime(datetime.datetime.now().timetuple()))
    self.browser_color = {'chrome': 'green', 'ie': 'blue', 'ff': 'red',
        'safari':'black'}
    self.values_list = values_list
    self.platform_list = platform_list
    self.revision_dict = dict()
    self.values_dict = dict()
    self.color_index = 0
    for platform in platform_list:
      self.revision_dict[platform] = dict()
      self.values_dict[platform] = dict()
      for f in v8_and_or_frog_list:
        self.revision_dict[platform][f] = dict()
        self.values_dict[platform][f] = dict()
        for val in values_list:
          self.revision_dict[platform][f][val] = []
          self.values_dict[platform][f][val] = []
      if V8 in v8_and_or_frog_list:
        self.revision_dict[platform][V8][V8_MEAN] = []
        self.values_dict[platform][V8][V8_MEAN] = []
      if FROG in v8_and_or_frog_list:
        self.revision_dict[platform][FROG][FROG_MEAN] = []
        self.values_dict[platform][FROG][FROG_MEAN] = []
 
  def get_color(self):
    color = COLORS[self.color_index]
    self.color_index = (self.color_index + 1) % len(COLORS)
    return color

  def syle_and_save_perf_plot(self, chart_title, y_axis_label, size_x, size_y, 
      legend_loc, filename, platform_list, v8_and_or_frog_list, values_list, 
      should_clear_axes=True):
    """Sets style preferences for chart boilerplate that is consistent across 
    all charts, and saves the chart as a png.
    Args:
      size_x the size of the printed chart, in inches, in the horizontal 
        direction
      size_y the size of the printed chart, in inches in the vertical direction
      legend_loc the location of the legend in on the chart. See suitable
        arguments for the loc argument in matplotlib
      filename the filename that we want to save the resulting chart as
      platform_list a list containing the platform(s) that our data has been run
        on. (command line, firefox, chrome, etc)
      values_list a list containing the type of data we will be graphing
        (performance, percentage passing, etc)
      should_clear_axes True if we want to create a fresh graph, instead of
        plotting additional lines on the current graph."""
    if should_clear_axes:
      plt.cla() # cla = clear current axes
    for platform in platform_list:
      for f in v8_and_or_frog_list:
        for val in values_list:
          plt.plot(self.revision_dict[platform][f][val],
              self.values_dict[platform][f][val], 
              color=self.get_color(), label='%s-%s-%s' % (platform, f, val))

    plt.xlabel('Revision Number')
    plt.ylabel(y_axis_label)
    plt.title(chart_title)
    fontP = FontProperties()
    fontP.set_size('small')
    plt.legend(loc=legend_loc, prop = fontP)

    fig = plt.gcf()
    fig.set_size_inches(size_x, size_y)
    fig.savefig(os.path.join(GRAPH_OUT_DIR, filename))

  def add_svn_revision_to_trace(self, outfile):
    """Add the svn version number to the provided tracefile."""
    p = subprocess.Popen(['svn', 'info'], stdout = subprocess.PIPE, 
      stderr = subprocess.STDOUT, shell = HAS_SHELL)
    output, not_used = p.communicate()
    for line in output.split('\n'):
      if 'Revision' in line:
        run_cmd(['echo', line.strip()], outfile)

  def write_html(self, delimiter, rev_nums, label_1, dict_1, label_2, dict_2, 
      cleanFile=False):
    """Adds an html table to the webpage to display the data values. This method
    will be removed when we have a nicer way to display data values."""
    #TODO(efortuna): fix this.
    return
    #TODO(efortuna): Take this method out when have finalized where the data is
    # going to be displayed.
    f = ''
    out = ''
    if cleanFile:
      f = open('template.html')
    else:
      shutil.copy('index.html', 'temp.html')
      f = open('temp.html')
    out = open('index.html', 'w')
    inTable = False
    for line in f.readlines():
      if not inTable:
        out.write(line)
      if delimiter in line:
        inTable = not inTable
        if inTable:
          out.write('<table border="1"> <tr> <td> svn revision </td>')
          for revision in rev_nums:
            out.write('<td>%d</td>' % revision)
          out.write('</tr>\n<tr><td> %s</td>' % label_1)
          for perf in dict_1:
            out.write('<td>%f</td>' % perf)
          out.write('</tr>\n<tr><td> %s</td>' % label_2)
          for perf in dict_2:
            out.write('<td>%f</td>' % perf)
          out.write('</tr> </table>')

  def calculate_geometric_mean(self, platform, frog_or_v8, svn_revision):
    """Calculate the aggregate geometric mean for V8 and frog benchmark sets,
    given two benchmark dictionaries."""
    geo_mean = 0
    for benchmark in get_benchmarks():
      geo_mean += math.log(self.values_dict[platform][frog_or_v8][benchmark][
          len(self.values_dict[platform][frog_or_v8][benchmark]) - 1])
 
    mean = V8_MEAN
    if frog_or_v8 == FROG:
       mean = FROG_MEAN
    self.values_dict[platform][frog_or_v8][mean] += \
        [math.pow(math.e, geo_mean / len(get_benchmarks()))]
    self.revision_dict[platform][frog_or_v8][mean] += [svn_revision]

  def run(self):
    """Run the benchmarks/tests from the command line and plot the 
    results."""
    if PERFBOT_MODE:
      plt.cla() # cla = clear current axes
    os.chdir(DART_INSTALL_LOCATION)
    ensure_output_directory(self.result_folder_name)
    ensure_output_directory(GRAPH_OUT_DIR)
    self.run_tests()
    os.chdir(os.path.join('tools', 'testing', 'perf_testing'))
    
    # TODO(efortuna): You will want to make this only use a subset of the files
    # eventually.
    files = os.listdir(self.result_folder_name)

    for afile in files:
      if not afile.startswith('.'):
        self.process_file(afile)

    if PERFBOT_MODE:
      self.plot_results('%s.png' % self.result_folder_name)

class PerformanceTestRunner(TestRunner):
  """Super class for all performance testing."""
  def __init__(self, result_folder_name, platform_list, platform_type):
    super(PerformanceTestRunner, self).__init__(result_folder_name, 
        platform_list, get_versions(), get_benchmarks())
    self.platform_list = platform_list
    self.platform_type = platform_type

  def plot_all_perf(self, png_filename):
    """Create a plot that shows the performance changes of individual benchmarks
    run by V8 and generated by frog, over svn history."""
    for benchmark in get_benchmarks():
      self.syle_and_save_perf_plot(
          'Performance of %s over time on the %s' % (benchmark,
          self.platform_type), 'Speed (bigger = better)', 16, 14, 'lower left', 
          benchmark + png_filename, self.platform_list, get_versions(), 
          [benchmark])

  def plot_avg_perf(self, png_filename):
    """Generate a plot that shows the performance changes of the geomentric mean
    of V8 and frog benchmark performance over svn history."""
    (title, y_axis, size_x, size_y, loc, filename) = \
        ('Geometric Mean of benchmark %s performance' % self.platform_type, 
        'Speed (bigger = better)', 16, 5, 'center', 'avg'+png_filename)
    for platform in self.platform_list:
      self.syle_and_save_perf_plot(title, y_axis, size_x, size_y, loc, filename, 
          [platform], [V8], [V8_MEAN], True)
      self.syle_and_save_perf_plot(title, y_axis, size_x, size_y, loc, filename, 
          [platform], [FROG], [FROG_MEAN], False)
      self.write_html('table', 
          self.revision_dict[platform][V8], 
          'V8 mean', self.values_dict[platform][V8][V8_MEAN],
          'Frog mean', self.values_dict[platform][FROG][FROG_MEAN], 
          True)

  def plot_results(self, png_filename):
    self.plot_all_perf(png_filename)
    self.plot_avg_perf('2' + png_filename)

  
class CommandLinePerformanceTestRunner(PerformanceTestRunner):
  """Run performance tests from the command line."""

  def __init__(self, result_folder_name):
    super(CommandLinePerformanceTestRunner, self).__init__(result_folder_name, 
        [COMMAND_LINE], 'command line')

  def process_file(self, afile):
    """Pull all the relevant information out of a given tracefile.

    Args:
      afile is the filename string we will be processing."""
    f = open(os.path.join(self.result_folder_name, afile))
    tabulate_data = False
    revision_num = 0
    for line in f.readlines():
      if 'Revision' in line:
        revision_num = int(line.split()[1])
      elif 'Benchmark' in line:
        tabulate_data = True
      elif tabulate_data:
        tokens = line.split()
        if len(tokens) < 4 or tokens[0] not in get_benchmarks():
          #Done tabulating data.
          break
        v8_value = float(tokens[1])
        frog_value = float(tokens[3])
        if v8_value == 0 or frog_value == 0:
          #Then there was an error when this performance test was run. Do not 
          #count it in our numbers.
          return
        benchmark = tokens[0]
        self.revision_dict[COMMAND_LINE][V8][benchmark] += [revision_num]
        self.values_dict[COMMAND_LINE][V8][benchmark] += [v8_value]
        self.revision_dict[COMMAND_LINE][FROG][benchmark] += [revision_num]
        self.values_dict[COMMAND_LINE][FROG][benchmark] += [frog_value]
    f.close()

    self.calculate_geometric_mean(COMMAND_LINE, FROG, revision_num)
    self.calculate_geometric_mean(COMMAND_LINE, V8, revision_num)
  
  def run_tests(self):
    """Run a performance test on our updated system."""
    os.chdir('frog')
    self.trace_file = os.path.join('..', 'tools', 'testing', 'perf_testing',
        self.result_folder_name, 'result' + self.cur_time)
    run_cmd(['python', os.path.join('benchmarks', 'perf_tests.py')],
        self.trace_file)
    os.chdir('..')


class BrowserPerformanceTestRunner(PerformanceTestRunner):
  """Runs performance tests, in the browser."""

  def __init__(self, result_folder_name):
    super(BrowserPerformanceTestRunner, self).__init__(
        result_folder_name, get_browsers(), 'browser')

  def run_tests(self):
    """Run a performance test in the browser."""
      # For the smoke test, just run a simple test, not the actual benchmarks to
      # ensure we haven't broken the Firefox DOM.

    os.chdir('frog')
    if PERFBOT_MODE:
      run_cmd(['python', os.path.join('benchmarks', 'make_web_benchmarks.py')])
    else:
      run_cmd(['./minfrog', '--out=../tools/testing/perf_testing/smoketest/' + \
      'smoketest_frog.js', '--libdir=%s/lib' % os.getcwd(),
      '--compile-only', '../tools/testing/perf_testing/smoketest/' + \
      'dartWebBase.dart'])
    os.chdir('..')

    for browser in get_browsers():
      for version in get_versions():
        self.trace_file = os.path.join('tools', 'testing', 'perf_testing', 
            self.result_folder_name,
            'perf-%s-%s-%s' % (self.cur_time, browser, version))
        self.add_svn_revision_to_trace(self.trace_file)
        file_path = os.path.join(os.getcwd(), 'internal', 'browserBenchmarks', 
            'benchmark_page_%s.html' % version)
        if not PERFBOT_MODE:
          file_path = os.path.join(os.getcwd(), 'tools', 'testing',
              'perf_testing', 'smoketest', 'smoketest_%s.html' % version)
        run_cmd(['python', os.path.join('tools', 'testing', 'run_selenium.py'), 
            '--out', file_path, '--browser', browser, 
            '--timeout', '600', '--perf'], self.trace_file, append=True)

  def process_file(self, afile):
    """Comb through the html to find the performance results."""
    parts = afile.split('-')
    browser = parts[2] 
    version = parts[3]
    f = open(os.path.join(self.result_folder_name, afile))
    lines = f.readlines()
    line = ''
    i = 0
    revision_num = 0
    while '<div id="results">' not in line and i < len(lines):
      if 'Revision' in line:
        revision_num = int(line.split()[1])
      line = lines[i]
      i += 1

    if i >= len(lines) or revision_num == 0:
      # Then this run did not complete. Ignore this tracefile. or in the case of
      # the smoke test, report an error.
      if not PERFBOT_MODE:
        print 'FAIL %s %s' % (browser, version)
        os.remove(os.path.join(self.result_folder_name, afile))
      return

    line = lines[i]
    i += 1
    results = []
    if line.find('<br>') > -1:
      results = line.split('<br>')
    else:
      results = line.split('<br />')
    for result in results:
      name_and_score = result.split(':')
      if len(name_and_score) < 2: 
        break
      name = name_and_score[0].strip()
      score = name_and_score[1].strip()
      if version == V8:
        bench_dict = self.values_dict[browser][V8]
      else:
        bench_dict = self.values_dict[browser][FROG]
      bench_dict[name] += [float(score)]
      self.revision_dict[browser][version][name] += [revision_num]

    f.close()
    if not PERFBOT_MODE:
      print 'PASS'
      os.remove(os.path.join(self.result_folder_name, afile))
    else:
      self.calculate_geometric_mean(browser, version, revision_num)

  def write_html(self, delimiter, rev_nums, label_1, dict_1, label_2, dict_2, 
      cleanFile=False):
      #TODO(efortuna)
      pass

      
class BrowserCorrectnessTestRunner(TestRunner):
  def __init__(self, test_type, result_folder_name):
    super(BrowserCorrectnessTestRunner, self).__init__(result_folder_name,
        get_browsers(), [FROG], [CORRECTNESS])
    self.test_type = test_type

  def run_tests(self):
    """run a test of the latest svn revision."""
    for browser in get_browsers():
      current_file = 'correctness%s-%s' % (self.cur_time, browser)
      self.trace_file = os.path.join('tools', 'testing',
          'perf_testing', self.result_folder_name, current_file)
      self.add_svn_revision_to_trace(self.trace_file)
      dart_sdk = os.path.join(os.getcwd(), utils.GetBuildRoot(utils.GuessOS(),
          'release', 'ia32'), 'dart-sdk')
      run_cmd([os.path.join('.', 'tools', 'test.py'),
          '--component=webdriver', '--flag=%s' % browser, '--flag=--frog=%s' % \
          os.path.join(dart_sdk, 'bin', 'frogc'), '--report',
          '--flag=--froglib=%s' % os.path.join(dart_sdk, 'lib'),
          '--timeout=20', '--progress=color', '--mode=release', '-j1',
          self.test_type], self.trace_file, append=True)

  def process_file(self, afile):
    """Given a trace file, extract all the relevant information out of it to
    determine the number of correctly passing tests.
    
    Arguments:
      afile the filename string"""
    browser = afile.rpartition('-')[2]
    f = open(os.path.join(self.result_folder_name, afile))
    revision_num = 0
    lines = f.readlines()
    total_tests = 0
    num_failed = 0
    expect_fail = 0
    for line in lines:
      if 'Total:' in line:
        total_tests = int(line.split()[1])
      if 'will be skipped' in line:
        total_tests -= int(line.split()[1])
      if 'we should fix' in line:
        expect_fail += int(line.split()[1])
      if 'Revision' in line:
        revision_num = int(line.split()[1])
      if '--- TIMEOUT ---' in line or 'FAIL:' in line or 'PASS' in line:
        # (A printed out 'PASS' indicates we incorrectly passed a negative
        # test.)
        num_failed += 1
    
    self.revision_dict[browser][FROG][CORRECTNESS] += [revision_num]
    self.values_dict[browser][FROG][CORRECTNESS] += [100.0 * 
        (((float)(total_tests - (expect_fail + num_failed))) /total_tests)]
    f.close()

  def plot_results(self, png_filename):
    first_time = True
    for browser in get_browsers():
      self.syle_and_save_perf_plot('Percentage of language tests passing in '
          'different browsers', '% of tests passed', 8, 8, 'lower left', 
          png_filename, [browser], [FROG], [CORRECTNESS], first_time) 
      first_time = False


class CompileTimeAndSizeTestRunner(TestRunner):
  """Run tests to determine how long minfrog takes to compile, and the compiled 
  file output size of some benchmarking files."""
  def __init__(self, result_folder_name):
    super(CompileTimeAndSizeTestRunner, self).__init__(result_folder_name,
        [COMMAND_LINE], [FROG], ['Compiling on Dart VM', 'Bootstrapping',
        'minfrog', 'swarm', 'total'])
    self.failure_threshold = {'Compiling on Dart VM' : 1, 'Bootstrapping' : .5, 
        'minfrog' : 100, 'swarm' : 100, 'total' : 100}

  def run_tests(self):
    os.chdir('frog')
    self.trace_file = os.path.join('..', 'tools', 'testing', 'perf_testing', 
        self.result_folder_name, self.result_folder_name + self.cur_time)
    
    self.add_svn_revision_to_trace(self.trace_file)    

    elapsed = time_cmd([os.path.join('.', 'frog.py'), '--',
        '--out=minfrog', 'minfrog.dart'])
    run_cmd(['echo', '%f Compiling on Dart VM in production mode in seconds' 
        % elapsed], self.trace_file, append=True)
    elapsed = time_cmd([os.path.join('.', 'minfrog'), '--out=minfrog',
        'minfrog.dart', os.path.join('tests', 'hello.dart')])
    if elapsed < self.failure_threshold['Bootstrapping']:
      #minfrog didn't compile correctly. Stop testing now, because subsequent
      #numbers will be meaningless.
      return
    size = os.path.getsize('minfrog')
    run_cmd(['echo', '%f Bootstrapping time in seconds in production mode' % 
        elapsed], self.trace_file, append=True)
    run_cmd(['echo', '%d Generated checked minfrog size' % size],
        self.trace_file, append=True)

    run_cmd([os.path.join('.', 'minfrog'), ' --out=swarm-result ',
        '--compile-only', os.path.join('..', 'client', 'samples', 'swarm',
        'swarm.dart')])
    swarm_size = 0
    try:
      swarm_size = os.path.getsize('swarm-result')
    except OSError:
      pass #If compilation failed, continue on running other tests.

    run_cmd([os.path.join('.', 'minfrog'), '--out=total-result',
        '--compile-only', os.path.join('..', 'client', 'samples', 'total',
        'src', 'Total.dart')])
    total_size = 0
    try:
      total_size = os.path.getsize('total-result')
    except OSError:
      pass #If compilation failed, continue on running other tests.

    run_cmd(['echo', '%d Generated checked swarm size' % swarm_size], 
        self.trace_file, append=True) 
    
    run_cmd(['echo', '%d Generated checked total size' % total_size], 
        self.trace_file, append=True) 
    os.chdir('..')

  def process_file(self, afile):
    """Pull all the relevant information out of a given tracefile.
    Args:
      afile is the filename string we will be processing."""
    f = open(os.path.join(self.result_folder_name, afile))
    tabulate_data = False
    revision_num = 0
    for line in f.readlines():
      tokens = line.split()
      if 'Revision' in line:
        revision_num = int(line.split()[1])
      else:
        for metric in self.values_list:
          if metric in line:
            num = tokens[0]
            if num.find('.') == -1:
              num = int(num)
            else:
              num = float(num)
            self.values_dict[COMMAND_LINE][FROG][metric] += [num]
            self.revision_dict[COMMAND_LINE][FROG][metric] += [revision_num]
   
    if revision_num != 0: 
      for metric in self.values_list:
        self.revision_dict[COMMAND_LINE][FROG][metric].pop()
        self.revision_dict[COMMAND_LINE][FROG][metric] += [revision_num]
        # Fill 0 if compilation failed.
        if self.values_dict[COMMAND_LINE][FROG][metric][-1] < \
            self.failure_threshold[metric]:
          self.values_dict[COMMAND_LINE][FROG][metric] += [0]
          self.revision_dict[COMMAND_LINE][FROG][metric] += [revision_num]

    f.close()

  def plot_results(self, png_filename):
    self.syle_and_save_perf_plot('Compiled minfrog Sizes', 
        'Size (in bytes)', 10, 10, 'center', png_filename, [COMMAND_LINE],
        [FROG], ['swarm', 'total', 'minfrog'])
    self.write_html('bar', self.revision_dict[COMMAND_LINE][FROG]['minfrog'], 
        'minfrog size', self.values_dict[COMMAND_LINE][FROG]['minfrog'], '', [])

    self.syle_and_save_perf_plot('Time to compile and bootstrap', 
        'Seconds', 10, 10, 'center', '2' + png_filename, [COMMAND_LINE], [FROG],
        ['Bootstrapping', 'Compiling on Dart VM'])
    self.write_html('baz',
        self.revision_dict[COMMAND_LINE][FROG]['Bootstrapping'], 
        'Bootstrapping', self.values_dict[COMMAND_LINE][FROG]['Bootstrapping'],
        'Compiling on Dart VM', 
        self.values_dict[COMMAND_LINE][FROG]['Compiling on Dart VM'])


def parse_args():
  parser = optparse.OptionParser()
  parser.add_option('--command-line', '-c', dest='cl', 
      help = 'Run the command line tests', 
      action = 'store_true', default = False) 
  parser.add_option('--size-time', '-s', dest = 'size', 
      help = 'Run the code size and timing tests', 
      action = 'store_true', default = False)
  parser.add_option('--language', '-l', dest = 'language', 
      help = 'Run the language correctness tests', 
      action = 'store_true', default = False)
  parser.add_option('--browser-perf', '-b', dest = 'perf',
      help = 'Run the browser performance tests',
      action = 'store_true', default = False)
  parser.add_option('--forever', '-f', dest = 'continuous',
      help = 'Run this script forever, always checking for the next svn '
      'checkin', action = 'store_true', default = False)
  parser.add_option('--perfbot', '-p', dest = 'perfbot',
      help = "Run in perfbot mode. (Generate plots, and keep trace files)", 
      action = 'store_true', default = False)
  parser.add_option('--verbose', '-v', dest = 'verbose',
      help = 'Print extra debug output', action = 'store_true', default = False)

  args, ignored = parser.parse_args()
  if not (args.cl or args.size or args.language or args.perf):
    args.cl = args.size = args.language = args.perf = True
  return (args.cl, args.size, args.language, args.perf, args.continuous,
      args.perfbot, args.verbose)

def run_test_sequence(cl, size, language, perf):
  if PERFBOT_MODE:
    # The buildbot already builds and syncs to a specific revision. Don't fight
    # with it or replicate work.
    if sync_and_build() == 1:
      return # The build is broken.
  if cl:
    CommandLinePerformanceTestRunner('cl-results').run()
  if size:
    CompileTimeAndSizeTestRunner('code-time-size').run()
  if language:
    BrowserCorrectnessTestRunner('language', 'browser-correctness').run()
  if perf:
    BrowserPerformanceTestRunner('browser-perf').run()

  if PERFBOT_MODE:
    upload_to_app_engine()

def main():
  global PERFBOT_MODE, VERBOSE
  (cl, size, language, perf, continuous, perfbot, verbose) = parse_args()
  PERFBOT_MODE = perfbot
  VERBOSE = verbose
  if continuous:
    while True:
      if has_new_code():
        run_test_sequence(cl, size, language, perf)
      else:
        time.sleep(SLEEP_TIME)
  else:
    run_test_sequence(cl, size, language, perf)

if __name__ == '__main__':
  main()

