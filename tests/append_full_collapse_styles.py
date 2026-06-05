import os

file_path = r'e:\code\web\work\aIELTS\frontend\src\styles\profile_page.css'
new_styles = """

/* Full Collapsible Sidebar Styles */
.manual-sidebar-wrapper {
    position: relative;
    width: 300px;
    transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 10;
}

.manual-sidebar-wrapper.closed {
    width: 0;
    margin-right: -15px; /* Adjust gap when closed */
}

/* Floating Toggle Handle */
.manual-toggle-handle {
    position: absolute;
    right: -15px;
    top: 50%;
    transform: translateY(-50%);
    width: 30px;
    height: 60px;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 0 10px 10px 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    box-shadow: 4px 0 10px rgba(59, 130, 246, 0.2);
    transition: all 0.3s ease;
    z-index: 20;
    padding-left: 2px;
}

.manual-toggle-handle:hover {
    width: 35px;
    background: #2563eb;
}

.manual-sidebar-wrapper.closed .manual-toggle-handle {
    right: -30px;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.sidebar-fully-closed .manual-sidebar {
    opacity: 0;
    pointer-events: none;
    transform: translateX(-20px);
}

.manual-sidebar {
    height: 100%;
    width: 100%;
    transition: opacity 0.3s ease, transform 0.4s ease;
}

/* Hide toggle in old header location */
.manual-sidebar-toggle {
    display: none !important;
}

/* Responsive adjustment for full screen */
.manual-container.sidebar-fully-closed .manual-content {
    padding-left: 20px;
}
"""

with open(file_path, 'a', encoding='utf-8') as f:
    f.write(new_styles)

print("Success")
