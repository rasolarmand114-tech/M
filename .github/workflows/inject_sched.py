#!/usr/bin/env python3
"""
arg/scripts/inject_sched.py
Patches kernel/sched/ for ARG hook infrastructure.
Called from CI before kernel build.
"""
import os, sys

SCHED = "kernel/sched"

# ── 1. arg_hook.c ─────────────────────────────────────────────────────
ARG_HOOK_C = """\
// SPDX-License-Identifier: GPL-2.0
#include <linux/export.h>
#include <linux/sched.h>
#include "sched.h"

bool arg_enabled __read_mostly = false;
EXPORT_SYMBOL_GPL(arg_enabled);

struct task_struct *(*arg_pick_next_hook)(struct rq *rq)
\t\t__read_mostly = NULL;
EXPORT_SYMBOL_GPL(arg_pick_next_hook);

void (*arg_enqueue_hook)(struct rq *rq, struct task_struct *p)
\t\t__read_mostly = NULL;
EXPORT_SYMBOL_GPL(arg_enqueue_hook);

void (*arg_wakeup_hook)(struct rq *rq, struct task_struct *p)
\t\t__read_mostly = NULL;
EXPORT_SYMBOL_GPL(arg_wakeup_hook);

void (*arg_update_load_hook)(void) __read_mostly = NULL;
EXPORT_SYMBOL_GPL(arg_update_load_hook);

/* runqueues: Samsung A12 kernel export nkarде.
 * cpu_rq() macro dar shim.c be in niaz dare.
 * age duplicate export error dad in blok ra hazf kon. */
DECLARE_PER_CPU_SHARED_ALIGNED(struct rq, runqueues);
EXPORT_SYMBOL(runqueues);
"""

dst = os.path.join(SCHED, "arg_hook.c")
if not os.path.exists(dst):
    with open(dst, "w") as f:
        f.write(ARG_HOOK_C)
    print("OK arg_hook.c written")
else:
    print("OK arg_hook.c already exists")

# ── 2. Kconfig ────────────────────────────────────────────────────────
KCONFIG_ADDITION = """
config SCHAD_ARG
\tbool "ARG Scheduler Hook"
\tdepends on SMP
\tdefault n
\thelp
\t  ARG hook layer. Zero policy. Required by CONFIG_SCHAD_ARG_KMM.
"""

kconfig_path = os.path.join(SCHED, "Kconfig")
with open(kconfig_path, "r") as f:
    kconfig = f.read()

if "SCHAD_ARG" not in kconfig:
    with open(kconfig_path, "a") as f:
        f.write(KCONFIG_ADDITION)
    print("OK SCHAD_ARG added to Kconfig")
else:
    print("OK SCHAD_ARG already in Kconfig")

# ── 3. Kbuild or Makefile ─────────────────────────────────────────────
kbuild = os.path.join(SCHED, "Kbuild")
kmake  = os.path.join(SCHED, "Makefile")
build_file = kbuild if os.path.exists(kbuild) else kmake

with open(build_file, "r") as f:
    build = f.read()

if "arg_hook" not in build:
    with open(build_file, "a") as f:
        f.write("\nobj-$(CONFIG_SCHAD_ARG) += arg_hook.o\n")
    print(f"OK arg_hook.o added to {os.path.basename(build_file)}")
else:
    print(f"OK arg_hook.o already in {os.path.basename(build_file)}")

# ── 4. sched.h — insert before last #endif ────────────────────────────
ARG_SCHED_H = """
/* ARG Scheduler Hook — begin */
#ifdef CONFIG_SCHAD_ARG
extern bool arg_enabled;
extern struct task_struct *(*arg_pick_next_hook)(struct rq *rq);
extern void (*arg_enqueue_hook)(struct rq *rq, struct task_struct *p);
extern void (*arg_wakeup_hook)(struct rq *rq, struct task_struct *p);
extern void (*arg_update_load_hook)(void);

static __always_inline struct task_struct *
arg_call_pick_next(struct rq *rq)
{
\tstruct task_struct *(*fn)(struct rq *);
\tif (!smp_load_acquire(&arg_enabled))
\t\treturn NULL;
\tfn = smp_load_acquire(&arg_pick_next_hook);
\treturn fn ? fn(rq) : NULL;
}
static __always_inline void
arg_call_enqueue(struct rq *rq, struct task_struct *p)
{
\tvoid (*fn)(struct rq *, struct task_struct *);
\tif (!smp_load_acquire(&arg_enabled))
\t\treturn;
\tfn = smp_load_acquire(&arg_enqueue_hook);
\tif (fn) fn(rq, p);
}
#else
static __always_inline struct task_struct *
arg_call_pick_next(struct rq *rq) { return NULL; }
static __always_inline void
arg_call_enqueue(struct rq *rq, struct task_struct *p) {}
#endif /* CONFIG_SCHAD_ARG */
/* ARG Scheduler Hook — end */
"""

sched_h = os.path.join(SCHED, "sched.h")
with open(sched_h, "r") as f:
    content = f.read()

if "arg_call_pick_next" not in content:
    idx = content.rfind("#endif")
    if idx == -1:
        print("ERROR: no #endif in sched.h", file=sys.stderr)
        sys.exit(1)
    content = content[:idx] + ARG_SCHED_H + content[idx:]
    with open(sched_h, "w") as f:
        f.write(content)
    print("OK sched.h patched")
else:
    print("OK sched.h already patched")

# ── 5. core.c — enqueue + pick_next hooks ────────────────────────────
core_c = os.path.join(SCHED, "core.c")
with open(core_c, "r") as f:
    content = f.read()

changed = False

TARGET_ENQ = "\tp->sched_class->enqueue_task(rq, p, flags);"
HOOK_ENQ = (
    "#ifdef CONFIG_SCHAD_ARG\n"
    "\targ_call_enqueue(rq, p);\n"
    "#endif\n"
    + TARGET_ENQ
)
if "arg_call_enqueue" not in content:
    if TARGET_ENQ in content:
        content = content.replace(TARGET_ENQ, HOOK_ENQ, 1)
        changed = True
        print("OK enqueue hook added")
    else:
        print("WARNING: enqueue target not found in core.c")
else:
    print("OK enqueue hook already present")

TARGET_PICK = "\tconst struct sched_class *class = &fair_sched_class;"
HOOK_PICK = (
    "#ifdef CONFIG_SCHAD_ARG\n"
    "\tif (!rq->rt.rt_nr_running) {\n"
    "\t\tstruct task_struct *arg_p = arg_call_pick_next(rq);\n"
    "\t\tif (arg_p) return arg_p;\n"
    "\t}\n"
    "#endif\n"
    + TARGET_PICK
)
if "arg_call_pick_next" not in content:
    if TARGET_PICK in content:
        content = content.replace(TARGET_PICK, HOOK_PICK, 1)
        changed = True
        print("OK pick_next hook added")
    else:
        print("WARNING: pick_next target not found in core.c")
else:
    print("OK pick_next hook already present")

if changed:
    with open(core_c, "w") as f:
        f.write(content)

print("\nDone. Verification:")
print(f"  arg_hook.c : {os.path.exists(dst)}")
print(f"  Kconfig    : {'SCHAD_ARG' in open(kconfig_path).read()}")
print(f"  sched.h    : {'arg_call_pick_next' in open(sched_h).read()}")
print(f"  core.c     : {'arg_call_enqueue' in open(core_c).read()}")
