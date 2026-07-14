import sys
import re

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')
    new_lines = []

    if "drying.py" in filepath:
        for line in lines:
            if "return cu.fetchall()" in line and "    " not in line:
                 new_lines.append(line.replace("+        return cu.fetchall()", "        return cu.fetchall()"))
            elif "return cu.fetchall()" in line:
                new_lines.append(line)
            else:
                 new_lines.append(line)
    elif "final_quality.py" in filepath:
        for line in lines:
            if "nonlocal current_total" in line:
                pass
            else:
                new_lines.append(line)
    elif "monitoring_warehouse.py" in filepath:
        for line in lines:
            if "nonlocal selected_request" in line:
                pass
            else:
                new_lines.append(line)
    elif "product_base.py" in filepath:
        for line in lines:
            if "nonlocal selected_product_code" in line or "nonlocal selected_codes" in line:
                pass
            else:
                new_lines.append(line)

    with open(filepath, 'w') as f:
        f.write('\n'.join(new_lines))

# fix_file("pages/drying.py")
# fix_file("pages/final_quality.py")
# fix_file("pages/monitoring_warehouse.py")
# fix_file("pages/product_base.py")
