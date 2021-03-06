// Copyright (c) 2016, the Dart project authors.  Please see the AUTHORS file
// for details. All rights reserved. Use of this source code is governed by a
// BSD-style license that can be found in the LICENSE file.

#include "vm/kernel.h"
#include "vm/compiler/frontend/kernel_binary_flowgraph.h"

#if !defined(DART_PRECOMPILED_RUNTIME)
namespace dart {

namespace kernel {

bool FieldHasFunctionLiteralInitializer(const Field& field,
                                        TokenPosition* start,
                                        TokenPosition* end) {
  Zone* zone = Thread::Current()->zone();
  const Script& script = Script::Handle(zone, field.Script());

  TranslationHelper translation_helper(Thread::Current());
  translation_helper.InitFromScript(script);

  StreamingFlowGraphBuilder builder(&translation_helper, field.Script(), zone,
                                    TypedData::Handle(zone, field.KernelData()),
                                    field.KernelDataProgramOffset());
  builder.SetOffset(field.kernel_offset());
  kernel::FieldHelper field_helper(&builder);
  field_helper.ReadUntilExcluding(kernel::FieldHelper::kEnd, true);
  return field_helper.FieldHasFunctionLiteralInitializer(start, end);
}

}  // namespace kernel

}  // namespace dart
#endif  // !defined(DART_PRECOMPILED_RUNTIME)
