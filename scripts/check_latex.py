#!/usr/bin/env python3
import re
import os
import sys

main_file = sys.argv[1] if len(sys.argv) > 1 else 'report/dissertation_report.tex'

def expand_inputs(filepath):
    base_dir = os.path.dirname(filepath)
    with open(filepath, 'r') as f:
        content = f.read()
    def repl(match):
        inc_file = match.group(1)
        if not inc_file.endswith('.tex'):
            inc_file += '.tex'
        full_path = os.path.join(base_dir, inc_file)
        if os.path.exists(full_path):
            return expand_inputs(full_path)
        return match.group(0)
    return re.sub(r'\\input\{([^}]+)\}', repl, content)

text = expand_inputs(main_file)

# 1. Environment check
begin_envs = re.findall(r'\\begin\{([^}]+)\}', text)
end_envs = re.findall(r'\\end\{([^}]+)\}', text)
print(f'Total \\begin: {len(begin_envs)}, Total \\end: {len(end_envs)}')

stack = []
lines = text.splitlines()
errors = []
for i, line in enumerate(lines, 1):
    clean_line = re.sub(r'(?<!\\)%.*$', '', line)
    for m in re.finditer(r'\\begin\{([^}]+)\}', clean_line):
        env = m.group(1)
        stack.append((env, i))
    for m in re.finditer(r'\\end\{([^}]+)\}', clean_line):
        env = m.group(1)
        if not stack:
            errors.append(f'Unmatched \\end{{{env}}} at line {i}')
        else:
            last_env, start_line = stack.pop()
            if last_env != env:
                errors.append(f'Mismatch: \\begin{{{last_env}}} at line {start_line} closed by \\end{{{env}}} at line {i}')

if stack:
    for env, start_line in stack:
        errors.append(f'Unclosed \\begin{{{env}}} from line {start_line}')

print(f'Environment check errors: {len(errors)}')
for e in errors[:10]:
    print(' ', e)

# 2. Labels and refs
labels = set(re.findall(r'\\label\{([^}]+)\}', text))
refs = set(re.findall(r'\\(?:ref|eqref|pageref)\{([^}]+)\}', text))
missing_refs = refs - labels
print(f'Total labels: {len(labels)}, Total refs: {len(refs)}')
print(f'Missing refs: {len(missing_refs)}')
for r in sorted(missing_refs):
    print('  Missing ref:', r)

# 3. Citations and bibitems
bibitems = set(re.findall(r'\\bibitem\{([^}]+)\}', text))
cites = set()
for c_group in re.findall(r'\\cite\{([^}]+)\}', text):
    for c in c_group.split(','):
        cites.add(c.strip())
missing_cites = cites - bibitems
print(f'Total bibitems: {len(bibitems)}, Total cited keys: {len(cites)}')
print(f'Missing cites: {len(missing_cites)}')
for c in sorted(missing_cites):
    print('  Missing cite:', c)

# 4. Graphics files
graphics = re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text)
base_dir = os.path.dirname(main_file)
missing_graphics = []
for g in graphics:
    g_path = os.path.join(base_dir, g)
    if not os.path.exists(g_path) and not os.path.exists(g_path + '.png') and not os.path.exists(g_path + '.pdf'):
        missing_graphics.append(g)

print(f'Total graphics: {len(graphics)}')
print(f'Missing graphics: {len(missing_graphics)}')
for g in sorted(missing_graphics):
    print('  Missing graphic:', g)

if not errors and not missing_refs and not missing_cites and not missing_graphics:
    print('\n[SUCCESS] All LaTeX checks passed perfectly! Ready for Overleaf compile.')
    sys.exit(0)
else:
    sys.exit(1)
