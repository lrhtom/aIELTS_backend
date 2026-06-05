import os

file_path = r'e:\code\web\work\aIELTS\frontend\src\styles\profile_page.css'
new_styles = """

/* Sidebar Toggle Improvements */
.manual-header-left {
    display: flex;
    align-items: center;
    gap: 15px;
}

.manual-sidebar-toggle {
    background: rgba(59, 130, 246, 0.1);
    border: none;
    color: #3b82f6;
    width: 36px;
    height: 36px;
    border-radius: 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    transition: all 0.3s ease;
}

.manual-sidebar-toggle:hover {
    background: #3b82f6;
    color: white;
    transform: scale(1.05);
}

.manual-sidebar.collapsed {
    width: 80px;
    padding: 15px 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.manual-sidebar.collapsed .manual-nav {
    align-items: center;
    width: 100%;
}

.manual-sidebar.collapsed .manual-nav-group {
    width: 100%;
    display: flex;
    justify-content: center;
}

.manual-sidebar.collapsed .manual-group-trigger {
    justify-content: center;
    padding: 15px 0;
    width: 50px;
    height: 50px;
    border-radius: 12px;
}

.manual-sidebar.collapsed .group-icon {
    font-size: 20px;
}

/* Ensure smooth width transition */
.manual-sidebar {
    transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1), padding 0.4s ease, background 0.3s ease;
}

.manual-container.sidebar-collapsed .manual-layout {
    gap: 15px;
}
"""

with open(file_path, 'a', encoding='utf-8') as f:
    f.write(new_styles)

print("Success")
