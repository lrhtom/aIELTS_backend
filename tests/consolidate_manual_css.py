import os

file_path = r'e:\code\web\work\aIELTS\frontend\src\styles\profile_page.css'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We want to remove everything from "/* Website Manual Optimized Styles */" to the end
start_index = -1
for i, line in enumerate(lines):
    if "/* Website Manual Optimized Styles */" in line:
        start_index = i
        break

if start_index != -1:
    lines = lines[:start_index]

new_manual_css = """
/* Website Manual - Total Hide Edition */
.manual-container.optimized {
    padding: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    position: relative;
    overflow: hidden;
}

.manual-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 25px;
    transition: all 0.3s ease;
}

.manual-header h2 {
    font-size: 26px;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
    letter-spacing: -0.5px;
}

/* Search Bar */
.manual-search-wrapper {
    position: relative;
    width: 320px;
}

.manual-search-input {
    width: 100%;
    padding: 10px 40px;
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(0, 0, 0, 0.05);
    border-radius: 12px;
    font-size: 14px;
    color: #1e293b;
    transition: all 0.3s ease;
}

.manual-search-input:focus {
    background: white;
    border-color: #3b82f6;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
    outline: none;
}

.manual-search-wrapper .search-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    opacity: 0.4;
}

/* Layout */
.manual-layout {
    display: flex;
    gap: 20px;
    flex: 1;
    min-height: 0;
    position: relative;
}

/* Sidebar Wrapper & Toggle */
.manual-sidebar-wrapper {
    position: relative;
    width: 280px;
    transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1), margin 0.4s ease;
    flex-shrink: 0;
}

.manual-sidebar-wrapper.closed {
    width: 0;
    margin-right: -10px;
}

.manual-sidebar {
    height: 100%;
    width: 280px; /* Fixed width inside wrapper */
    padding: 15px;
    overflow-y: auto;
    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.8);
    transition: opacity 0.3s ease, transform 0.3s ease;
}

.manual-sidebar-wrapper.closed .manual-sidebar {
    opacity: 0;
    pointer-events: none;
    transform: translateX(-20px);
}

/* Floating Handle */
.manual-toggle-handle {
    position: absolute;
    right: -12px;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 48px;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 0 8px 8px 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    box-shadow: 2px 0 8px rgba(59, 130, 246, 0.3);
    z-index: 100;
    transition: all 0.2s ease;
}

.manual-sidebar-wrapper.closed .manual-toggle-handle {
    right: -24px;
    border-radius: 8px;
}

.manual-toggle-handle:hover {
    background: #2563eb;
    width: 28px;
}

/* Menu Items */
.manual-nav-group { margin-bottom: 8px; }

.manual-group-trigger {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    background: transparent;
    border: none;
    color: #475569;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    border-radius: 12px;
    transition: all 0.2s;
}

.manual-group-trigger:hover { background: rgba(255, 255, 255, 0.8); }

.manual-group-trigger.expanded { color: #3b82f6; background: rgba(59, 130, 246, 0.05); }

.manual-group-trigger .chevron {
    width: 16px; height: 16px; margin-left: auto;
    transition: transform 0.3s ease;
}

.manual-group-trigger.expanded .chevron { transform: rotate(180deg); }

.manual-sub-list {
    max-height: 0; overflow: hidden;
    transition: all 0.3s ease;
    padding-left: 12px;
}

.manual-sub-list.open { max-height: 500px; padding-top: 4px; }

.manual-sub-item {
    width: 100%; text-align: left; padding: 8px 12px;
    border: none; background: transparent;
    color: #64748b; font-size: 14px;
    cursor: pointer; border-radius: 8px;
    transition: all 0.2s;
}

.manual-sub-item:hover { color: #3b82f6; background: white; transform: translateX(4px); }

.manual-sub-item.active {
    color: #3b82f6; background: white; font-weight: 700;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}

/* Content Area */
.manual-content {
    flex: 1;
    overflow-y: auto;
    min-width: 0;
}

.manual-detail-card {
    background: white;
    border-radius: 20px;
    padding: 40px;
    min-height: 100%;
    box-shadow: 0 4px 20px rgba(0,0,0,0.02);
}

.manual-breadcrumbs {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; font-weight: 700; color: #94a3b8;
    margin-bottom: 25px; text-transform: uppercase;
}

.detail-header { display: flex; align-items: center; gap: 20px; margin-bottom: 30px; }

.detail-icon {
    font-size: 36px; width: 70px; height: 70px;
    background: #f8fafc; border-radius: 18px;
    display: flex; align-items: center; justify-content: center;
}

.detail-titles h3 { font-size: 28px; font-weight: 800; color: #0f172a; margin: 4px 0 0 0; }

.detail-body { font-size: 16px; line-height: 1.8; color: #334155; }

.content-paragraph { background: #f8fafc; padding: 25px; border-radius: 16px; }

/* Animations */
@keyframes slideUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.fade-in { animation: fadeIn 0.4s ease-out; }
@keyframes fadeIn {
    from { opacity: 0; transform: translateX(10px); }
    to { opacity: 1; transform: translateX(0); }
}
"""

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
    f.write(new_manual_css)

print("Success")
