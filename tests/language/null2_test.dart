// Copyright (c) 2014, the Dart project authors.  Please see the AUTHORS file
// for details. All rights reserved. Use of this source code is governed by a
// BSD-style license that can be found in the LICENSE file.
// Second dart test program.

import "package:expect/expect.dart";

@AssumeDynamic()
@NoInline()
confuse(x) => x;

main() {
  Expect.equals("Null", null.runtimeType.toString());
  Expect.equals("Null", confuse(null).runtimeType.toString());
}
