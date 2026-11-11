import re

def update_file(filename, replacement_pairs):
    with open(filename, 'r') as f:
        text = f.read()
    
    # ensure useProject is imported if not already, or that globalDateRange is destructured
    if "globalDateRange" not in text:
        text = text.replace("const { currentProject } = useProject();", "const { currentProject, globalDateRange } = useProject();")
        text = text.replace("const pid = currentProject?.id ?? 0;", "const pid = currentProject?.id ?? 0;\n  const sd = globalDateRange?.from ? globalDateRange.from.toISOString() : undefined;\n  const ed = globalDateRange?.to ? globalDateRange.to.toISOString() : undefined;")

    for old, new in replacement_pairs:
        text = text.replace(old, new)

    with open(filename, 'w') as f:
        f.write(text)


update_file('src/pages/ClientProgress.tsx', [
    (
        'queryKey: ["client-progress", pid]',
        'queryKey: ["client-progress", pid, sd, ed]'
    ),
    (
        'queryFn: () => developerApi.getClientProgress(pid)',
        'queryFn: () => developerApi.getClientProgress(pid, undefined, sd, ed)'
    )
])

update_file('src/pages/VendorDashboard.tsx', [
    (
        'queryKey: ["vendor-devs", pid]',
        'queryKey: ["vendor-devs", pid, sd, ed]'
    ),
    (
        'queryFn: () => analyticsApi.getVendorDevelopers(pid)',
        'queryFn: () => analyticsApi.getVendorDevelopers(pid, sd, ed)'
    )
])

# For Developers.tsx (Team KPIs)
update_file('src/pages/Developers.tsx', [
    (
        'queryKey: ["team-kpis", pid]',
        'queryKey: ["team-kpis", pid, sd, ed]'
    ),
    (
        'queryFn: () => developerApi.getTeamKPIs(pid)',
        'queryFn: () => developerApi.getTeamKPIs(pid, undefined, sd, ed)'
    )
])

