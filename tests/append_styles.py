import os

file_path = r'e:\code\web\work\aIELTS\frontend\src\styles\profile_page.css'
new_styles = """

/* Website Manual Optimized Styles */
.manual-container.optimized {
    padding: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}

.manual-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
}

.manual-header h2 {
    font-size: 28px;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
    letter-spacing: -0.5px;
}

/* Search Bar */
.manual-search-wrapper {
    position: relative;
    width: 350px;
}

.manual-search-input {
    width: 100%;
    padding: 12px 45px;
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.9);
    border-radius: 14px;
    font-size: 15px;
    color: #1e293b;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.manual-search-input:focus {
    background: white;
    border-color: #3b82f6;
    box-shadow: 0 10px 15px -3px rgba(59, 130, 246, 0.1);
    outline: none;
    width: 380px;
}

.manual-search-wrapper .search-icon {
    position: absolute;
    left: 15px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 18px;
    opacity: 0.5;
}

.clear-search {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    background: #e2e8f0;
    border: none;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    font-size: 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}

.clear-search:hover {
    background: #cbd5e1;
}

/* Layout & Panels */
.manual-layout {
    display: flex;
    gap: 30px;
    flex: 1;
    min-height: 0;
}

.glass-panel {
    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(20px);
    border-radius: 24px;
    border: 1px solid rgba(255, 255, 255, 0.8);
    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.04);
}

.manual-sidebar {
    width: 300px;
    padding: 20px;
    overflow-y: auto;
}

.manual-sidebar::-webkit-scrollbar {
    width: 6px;
}

.manual-sidebar::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 10px;
}

/* Nav Styles */
.manual-nav-group {
    margin-bottom: 10px;
}

.manual-group-trigger {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    background: transparent;
    border: none;
    color: #334155;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    border-radius: 14px;
    transition: all 0.3s ease;
}

.manual-group-trigger:hover {
    background: rgba(255, 255, 255, 0.9);
    transform: translateX(4px);
}

.manual-group-trigger.expanded {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.05);
}

.manual-group-trigger .chevron {
    width: 18px;
    height: 18px;
    margin-left: auto;
    transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.manual-group-trigger.expanded .chevron {
    transform: rotate(180deg);
}

.manual-sub-list {
    max-height: 0;
    overflow: hidden;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
    padding-left: 15px;
    margin-top: 5px;
}

.manual-sub-list.open {
    max-height: 600px;
    opacity: 1;
}

.manual-sub-item {
    padding: 10px 15px;
    border: none;
    background: transparent;
    color: #64748b;
    font-size: 14.5px;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
    border-radius: 10px;
    transition: all 0.2s ease;
    margin-bottom: 4px;
    border-left: 2px solid transparent;
}

.manual-sub-item:hover {
    color: #3b82f6;
    background: rgba(255, 255, 255, 0.8);
    transform: translateX(8px);
}

.manual-sub-item.active {
    color: #3b82f6;
    background: white;
    font-weight: 700;
    border-left-color: #3b82f6;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

/* Content Area */
.manual-content {
    flex: 1;
    overflow-y: auto;
}

.manual-detail-card {
    background: white;
    padding: 50px;
    min-height: 100%;
}

.manual-breadcrumbs {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    color: #94a3b8;
    margin-bottom: 30px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.breadcrumb-separator {
    color: #cbd5e1;
}

.manual-breadcrumbs .current {
    color: #3b82f6;
}

.detail-header {
    display: flex;
    align-items: center;
    gap: 24px;
    margin-bottom: 40px;
}

.detail-icon {
    font-size: 44px;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    width: 90px;
    height: 90px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 24px;
    box-shadow: inset 0 2px 4px rgba(255, 255, 255, 1), 0 4px 12px rgba(0, 0, 0, 0.03);
}

.detail-titles h3 {
    font-size: 34px;
    font-weight: 900;
    color: #0f172a;
    margin: 6px 0 0 0;
    letter-spacing: -1px;
}

.detail-body {
    font-size: 17px;
    line-height: 1.9;
    color: #334155;
    max-width: 800px;
}

.content-paragraph {
    background: #f8fafc;
    padding: 30px;
    border-radius: 20px;
    border: 1px solid #f1f5f9;
}

/* Empty States */
.manual-empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #94a3b8;
    text-align: center;
}

.empty-icon {
    font-size: 60px;
    margin-bottom: 20px;
    filter: grayscale(1);
    opacity: 0.3;
}

.manual-nav-empty {
    padding: 40px 20px;
    text-align: center;
    color: #94a3b8;
    font-size: 14px;
}

/* Animations */
.fade-in {
    animation: fadeInContent 0.5s ease-out;
}

@keyframes fadeInContent {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: translateX(0); }
}

@keyframes slideUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 1200px) {
    .manual-layout {
        flex-direction: column;
    }
    .manual-sidebar {
        width: 100%;
        max-height: 300px;
    }
    .manual-search-wrapper {
        width: 250px;
    }
}
"""

with open(file_path, 'a', encoding='utf-8') as f:
    f.write(new_styles)

print("Success")
