import json
import subprocess

HEADER = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
"""


def _run(script, timeout=15):
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", HEADER + "\n" + script],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def _parse(stdout):
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def get_elements(max_items=500):
    max_items = max(1, int(max_items))
    script = f"""
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = [System.Windows.Automation.Condition]::TrueCondition
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
$output = @(); $count = 0
foreach ($element in $elements) {{
    if ($count -ge {max_items}) {{ break }}
    try {{
        $name=[string]$element.Current.Name
        $automationId=[string]$element.Current.AutomationId
        $className=[string]$element.Current.ClassName
        $controlType=[string]$element.Current.ControlType.ProgrammaticName
        $processId=[int]$element.Current.ProcessId
        $rect=$element.Current.BoundingRectangle
        if ($name -or $automationId -or $className) {{
            $output += [PSCustomObject]@{{name=$name;automation_id=$automationId;class_name=$className;control_type=$controlType;process_id=$processId;hwnd=[int64]$element.Current.NativeWindowHandle;x=[int]$rect.X;y=[int]$rect.Y;width=[int]$rect.Width;height=[int]$rect.Height}}
            $count++
        }}
    }} catch {{}}
}}
if ($output.Count -eq 0) {{ '[]' }} else {{ $output | ConvertTo-Json -Compress }}
"""
    rc, stdout, _ = _run(script)
    return _parse(stdout) if rc == 0 else []


def get_process_elements(process_id, max_items=1500):
    """Enumerate UIA elements for one Windows process.

    This is intentionally process-scoped. It is useful for packaged apps
    such as WhatsApp Desktop where a global descendant walk may return zero.
    """
    pid = int(process_id)
    max_items = max(1, int(max_items))
    script = f"""
$pidTarget={pid}
$root=[System.Windows.Automation.AutomationElement]::RootElement
$trueCondition=[System.Windows.Automation.Condition]::TrueCondition
$out=@(); $seen=@{{}}
function Add-E($e) {{
    try {{
        if ([int]$e.Current.ProcessId -ne $pidTarget) {{ return }}
        $name=[string]$e.Current.Name; $aid=[string]$e.Current.AutomationId; $cls=[string]$e.Current.ClassName; $type=[string]$e.Current.ControlType.ProgrammaticName; $rect=$e.Current.BoundingRectangle
        if (-not ($name -or $aid -or $cls)) {{ return }}
        $key=\"$name|$aid|$cls|$type|$([int]$rect.X)|$([int]$rect.Y)\"
        if ($seen.ContainsKey($key)) {{ return }}
        $seen[$key]=$true
        $script:out += [PSCustomObject]@{{name=$name;automation_id=$aid;class_name=$cls;control_type=$type;process_id=$pidTarget;hwnd=[int64]$e.Current.NativeWindowHandle;x=[int]$rect.X;y=[int]$rect.Y;width=[int]$rect.Width;height=[int]$rect.Height}}
    }} catch {{}}
}}
try {{
    $tops=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$trueCondition)
    foreach($top in $tops) {{
        try {{ if([int]$top.Current.ProcessId -eq $pidTarget) {{ Add-E $top; $desc=$top.FindAll([System.Windows.Automation.TreeScope]::Descendants,$trueCondition); foreach($e in $desc) {{ if($script:out.Count -ge {max_items}){{break}}; Add-E $e }} }} }} catch {{}}
        if($script:out.Count -ge {max_items}){{break}}
    }}
}} catch {{}}
if($out.Count -eq 0){{'[]'}}else{{$out|ConvertTo-Json -Compress}}
"""
    rc, stdout, _ = _run(script, timeout=20)
    return _parse(stdout) if rc == 0 else []


def find(name="", control_type="", automation_id="", class_name=""):
    name=str(name or "").strip().lower()
    control_type=str(control_type or "").strip().lower()
    automation_id=str(automation_id or "").strip().lower()
    class_name=str(class_name or "").strip().lower()
    matches=[]
    for element in get_elements():
        if name and name not in str(element.get("name","")).lower(): continue
        if control_type and control_type not in str(element.get("control_type","")).lower(): continue
        if automation_id and automation_id not in str(element.get("automation_id","")).lower(): continue
        if class_name and class_name not in str(element.get("class_name","")).lower(): continue
        matches.append(element)
    return matches


def find_process(process_id, name="", control_type="", automation_id="", class_name="", max_items=1500):
    name=str(name or "").strip().lower()
    control_type=str(control_type or "").strip().lower()
    automation_id=str(automation_id or "").strip().lower()
    class_name=str(class_name or "").strip().lower()
    matches=[]
    for element in get_process_elements(process_id, max_items=max_items):
        if name and name not in str(element.get("name","")).lower(): continue
        if control_type and control_type not in str(element.get("control_type","")).lower(): continue
        if automation_id and automation_id not in str(element.get("automation_id","")).lower(): continue
        if class_name and class_name not in str(element.get("class_name","")).lower(): continue
        matches.append(element)
    return matches


def _ps_quote(value):
    """Quote a value safely for a PowerShell single-quoted string."""
    return "'" + str(value or "").replace("'", "''") + "'"


def focus_process_element(process_id, name="", control_type="", automation_id="", class_name="", x=None, y=None):
    """Focus one UIA element inside a single process without mouse input."""
    pid = int(process_id)
    name = _ps_quote(name)
    control_type = _ps_quote(control_type)
    automation_id = _ps_quote(automation_id)
    class_name = _ps_quote(class_name)
    x_expr = "''" if x is None else str(int(x))
    y_expr = "''" if y is None else str(int(y))
    script = f"""
$pidTarget={pid}; $wantedName={name}; $wantedType={control_type}; $wantedAid={automation_id}; $wantedClass={class_name}; $wantedX={x_expr}; $wantedY={y_expr}
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=[System.Windows.Automation.Condition]::TrueCondition
$best=$null; $bestScore=999999999
try {{
  $tops=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
  foreach($top in $tops) {{
    try {{
      if([int]$top.Current.ProcessId -ne $pidTarget){{continue}}
      $all=@($top)+@($top.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond))
      foreach($e in $all) {{
        try {{
          if([int]$e.Current.ProcessId -ne $pidTarget){{continue}}
          $n=[string]$e.Current.Name; $t=[string]$e.Current.ControlType.ProgrammaticName; $a=[string]$e.Current.AutomationId; $c=[string]$e.Current.ClassName; $r=$e.Current.BoundingRectangle
          $score=0
          if($wantedName -and $n -ne $wantedName){{ if($n -notlike "*$wantedName*"){{continue}}; $score+=20 }}
          if($wantedType -and $t -notlike "*$wantedType*"){{continue}}
          if($wantedAid -and $a -ne $wantedAid){{continue}}
          if($wantedClass -and $c -ne $wantedClass){{continue}}
          if($wantedX -ne ''){{$score += [math]::Abs([int]$r.X-[int]$wantedX)}}
          if($wantedY -ne ''){{$score += [math]::Abs([int]$r.Y-[int]$wantedY)}}
          if($score -lt $bestScore){{$best=$e;$bestScore=$score}}
        }} catch {{}}
      }}
    }} catch {{}}
  }}
  if($best){{$best.SetFocus(); 'OK'}}else{{'NOT_FOUND'}}
}} catch {{'ERROR'}}
"""
    rc, stdout, stderr = _run(script, timeout=8)
    return rc == 0 and stdout.strip().endswith("OK")


def invoke_process_element(process_id, name="", control_type="", automation_id="", class_name="", x=None, y=None):
    """Activate one UIA element using UIA patterns; never moves the mouse."""
    pid = int(process_id)
    name = _ps_quote(name)
    control_type = _ps_quote(control_type)
    automation_id = _ps_quote(automation_id)
    class_name = _ps_quote(class_name)
    x_expr = "''" if x is None else str(int(x))
    y_expr = "''" if y is None else str(int(y))
    script = f"""
$pidTarget={pid}; $wantedName={name}; $wantedType={control_type}; $wantedAid={automation_id}; $wantedClass={class_name}; $wantedX={x_expr}; $wantedY={y_expr}
$root=[System.Windows.Automation.AutomationElement]::RootElement
$cond=[System.Windows.Automation.Condition]::TrueCondition
$best=$null; $bestScore=999999999
try {{
  $tops=$root.FindAll([System.Windows.Automation.TreeScope]::Children,$cond)
  foreach($top in $tops) {{
    try {{
      if([int]$top.Current.ProcessId -ne $pidTarget){{continue}}
      $all=@($top)+@($top.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond))
      foreach($e in $all) {{
        try {{
          if([int]$e.Current.ProcessId -ne $pidTarget){{continue}}
          $n=[string]$e.Current.Name; $t=[string]$e.Current.ControlType.ProgrammaticName; $a=[string]$e.Current.AutomationId; $c=[string]$e.Current.ClassName; $r=$e.Current.BoundingRectangle
          $score=0
          if($wantedName -and $n -ne $wantedName){{ if($n -notlike "*$wantedName*"){{continue}}; $score+=20 }}
          if($wantedType -and $t -notlike "*$wantedType*"){{continue}}
          if($wantedAid -and $a -ne $wantedAid){{continue}}
          if($wantedClass -and $c -ne $wantedClass){{continue}}
          if($wantedX -ne ''){{$score += [math]::Abs([int]$r.X-[int]$wantedX)}}
          if($wantedY -ne ''){{$score += [math]::Abs([int]$r.Y-[int]$wantedY)}}
          if($score -lt $bestScore){{$best=$e;$bestScore=$score}}
        }} catch {{}}
      }}
    }} catch {{}}
  }}
  if(-not $best){{'NOT_FOUND'; exit}}
  try {{ $p=$best.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern); $p.Invoke(); 'INVOKED'; exit }} catch {{}}
  try {{ $p=$best.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern); $p.Select(); 'SELECTED'; exit }} catch {{}}
  try {{ $best.SetFocus(); 'FOCUSED'; exit }} catch {{}}
}} catch {{'ERROR'}}
"""
    rc, stdout, stderr = _run(script, timeout=8)
    return rc == 0 and stdout.strip() in {"INVOKED", "SELECTED", "FOCUSED"}
