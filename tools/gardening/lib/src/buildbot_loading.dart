// Copyright (c) 2017, the Dart project authors.  Please see the AUTHORS file
// for details. All rights reserved. Use of this source code is governed by a
// BSD-style license that can be found in the LICENSE file.

import 'dart:async';
import 'dart:io';
import 'cache_new.dart';
import 'logdog_rpc.dart';
import 'results/util.dart';

import 'util.dart';

import 'buildbot_structures.dart';
import 'cache.dart';

const String BUILDBOT_BUILDNUMBER = ' BUILDBOT_BUILDNUMBER: ';
const String BUILDBOT_REVISION = ' BUILDBOT_REVISION: ';

/// Read the build result for [buildUri].
///
/// The data is loaded from the cache, if available, otherwise [read] is called
/// to fetch the data and stored in the cache afterwards.
Future<BuildResult> _readBuildResult(
    BuildUri buildUri, Future<String> read()) async {
  if (buildUri.buildNumber < 0) {
    String text = await read();
    BuildResult result = parseTestStepResult(buildUri, text);
    if (result.buildNumber != null) {
      cache.write(result.buildUri.logdogPath, text);
    }
    return result;
  } else {
    return parseTestStepResult(
        buildUri, await cache.read(buildUri.logdogPath, read));
  }
}

/// Fetches test data for [buildUri] through the buildbot stdio.
Future<BuildResult> readBuildResultFromHttp(
    HttpClient client, BuildUri buildUri,
    [Duration timeout]) {
  Future<String> read() async {
    Uri uri = buildUri.toUri();
    log('Reading buildbot results: $uri');
    return readUriAsText(client, uri, timeout);
  }

  return _readBuildResult(buildUri, read);
}

/// Fetches test data for [buildUri] through logdog.
///
/// The build number of [buildUri] most be non-negative.
Future<BuildResult> readBuildResultFromLogDog(BuildUri buildUri) {
  LogdogRpc logdog = new LogdogRpc();
  Future<String> read() {
    log('Reading logdog results: $buildUri');
    return logdog.get(BUILDER_PROJECT, buildUri.logdogPath, noCache()());
  }

  return _readBuildResult(buildUri, read);
}

/// Parses a test status line of the from
/// `Done <config-name> <arch-name> <test-name>: <status>`.
///
/// If [line] is not of the correct form, `null` is returned.
TestStatus parseTestStatus(String line) {
  try {
    List<String> parts = split(line, ['Done ', ' ', ' ', ': ']);
    String testName = parts[3];
    String configName = parts[1];
    String archName = parts[2];
    String status = parts[4];
    return new TestStatus(
        new TestConfiguration(configName, archName, testName), status);
  } catch (_) {
    return null;
  }
}

/// Parses the [buildUri] test log and creates a [BuildResult] for it.
BuildResult parseTestStepResult(BuildUri buildUri, String text) {
  log('Parsing results: $buildUri (${text.length} bytes)');
  int buildNumber;
  String buildRevision;
  List<String> currentFailure;
  bool parsingTimingBlock = false;

  List<TestStatus> results = <TestStatus>[];
  List<TestFailure> failures = <TestFailure>[];
  List<Timing> timings = <Timing>[];
  List<String> strings = text.split('\n');
  for (String line in strings) {
    if (line.startsWith(BUILDBOT_BUILDNUMBER)) {
      buildNumber =
          int.parse(line.substring(BUILDBOT_BUILDNUMBER.length).trim());
      buildUri = buildUri.withBuildNumber(buildNumber);
    }
    if (line.startsWith(BUILDBOT_REVISION)) {
      buildRevision = line.substring(BUILDBOT_REVISION.length).trim();
    }
    if (currentFailure != null) {
      if (line.startsWith('Done ')) {
        TestStatus status = parseTestStatus(line);
        if (status != null) {
          results.add(status);
          failures.add(new TestFailure(buildUri, currentFailure));
          currentFailure = null;
        }
      } else {
        currentFailure.add(line);
      }
    } else if (line.startsWith('FAILED:')) {
      currentFailure = <String>[];
      currentFailure.add(line);
    } else if (line.startsWith('Done ')) {
      TestStatus status = parseTestStatus(line);
      if (status != null) {
        results.add(status);
      }
    }
    if (line.startsWith('--- Total time:')) {
      parsingTimingBlock = true;
    } else if (parsingTimingBlock) {
      if (line.startsWith('0:')) {
        timings.addAll(parseTimings(buildUri, line));
      } else {
        parsingTimingBlock = false;
      }
    }
  }
  return new BuildResult(buildUri, buildNumber ?? buildUri.absoluteBuildNumber,
      buildRevision, results, failures, timings);
}

/// Create the [Timing]s for the [line] as found in the top-20 timings of a
/// build step stdio log.
List<Timing> parseTimings(BuildUri uri, String line) {
  List<String> parts = split(line, [' - ', ' - ', ' ']);
  String time = parts[0];
  String stepName = parts[1];
  String configName = parts[2];
  String testNames = parts[3];
  List<Timing> timings = <Timing>[];
  for (String name in testNames.split(',')) {
    name = name.trim();
    int slashPos = name.indexOf('/');
    String archName = name.substring(0, slashPos);
    String testName = name.substring(slashPos + 1);
    timings.add(new Timing(
        uri,
        time,
        new TestStep(
            stepName, new TestConfiguration(configName, archName, testName))));
  }
  return timings;
}
