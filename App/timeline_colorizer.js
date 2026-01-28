/**
 * Timeline Report Custom Colorizer
 * 
 * Copy and paste this into your browser's DevTools Console (F12 > Console)
 * when viewing a timeline report HTML file.
 * 
 * Customize the colors in the configuration section below!
 */

// ============================================================================
// CONFIGURATION - Edit these colors to match your preferences
// ============================================================================

const CONFIG = {
    // Colors for untracked statuses
    untrackedStatusColors: {
        'Awaiting Code Review': '#9C27B0',  // Purple
        'Awaiting Deployment': '#FF9800',   // Orange  
        'Awaiting QA': '#2196F3',           // Blue
        'Blocked': '#F44336',               // Red
        'On Hold': '#FFC107',               // Amber
        'In Review': '#4CAF50',             // Green
        'Awaiting Approval': '#E91E63',     // Pink
        'Awaiting Merge': '#00BCD4',        // Cyan
    },
    
    // Options
    addLabelsToWideSegments: true,  // Add status name to segments wider than 5%
    addIconsToSegments: false,       // Add emoji icons (set to true to enable)
    highlightBlockedIssues: true,   // Highlight entire row for blocked issues
    addBorderToUntracked: false,     // Add border around untracked segments
    
    // Icons for statuses (if addIconsToSegments is true)
    statusIcons: {
        'Awaiting Code Review': '👀',
        'Awaiting Deployment': '🚀',
        'Awaiting QA': '🔍',
        'Blocked': '🚫',
        'On Hold': '⏸️',
        'In Review': '📝',
        'Awaiting Approval': '✅',
        'Awaiting Merge': '🔀',
    }
};

// ============================================================================
// MAIN SCRIPT - You don't need to edit below this line
// ============================================================================

function applyCustomColors() {
    console.log('🎨 Applying custom colors to timeline report...');
    
    let appliedCount = 0;
    
    // Apply colors to each configured untracked status
    Object.entries(CONFIG.untrackedStatusColors).forEach(([status, color]) => {
        const selector = `[title^="Untracked: ${status}"]`;
        const elements = document.querySelectorAll(selector);
        
        elements.forEach(el => {
            el.style.backgroundColor = color;
            el.style.color = 'white';
            el.style.fontWeight = 'bold';
            
            // Add border if configured
            if (CONFIG.addBorderToUntracked) {
                el.style.border = '1px solid rgba(0,0,0,0.3)';
            }
            
            // Add label if segment is wide enough
            const width = parseFloat(el.style.width);
            if (width > 5 && CONFIG.addLabelsToWideSegments) {
                let label = status;
                
                // Add icon if configured
                if (CONFIG.addIconsToSegments && CONFIG.statusIcons[status]) {
                    label = CONFIG.statusIcons[status] + ' ' + label;
                }
                
                el.textContent = label;
            } else if (width > 2 && CONFIG.addIconsToSegments && CONFIG.statusIcons[status]) {
                // Just icon for narrow segments
                el.textContent = CONFIG.statusIcons[status];
            }
            
            appliedCount++;
        });
        
        if (elements.length > 0) {
            console.log(`  ✓ ${status}: ${elements.length} segments colored ${color}`);
        }
    });
    
    // Highlight blocked issues (entire row)
    if (CONFIG.highlightBlockedIssues) {
        document.querySelectorAll('[title*="Blocked"]').forEach(el => {
            const row = el.closest('.timeline-row');
            if (row) {
                row.style.backgroundColor = '#FFEBEE';
                row.style.borderLeft = '4px solid #F44336';
            }
        });
        console.log('  ✓ Blocked issues highlighted');
    }
    
    console.log(`\n✅ Complete! Applied custom colors to ${appliedCount} segments`);
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function discoverUntrackedStatuses() {
    console.log('\n📊 Discovering untracked statuses in this report...\n');
    
    const statusCounts = {};
    document.querySelectorAll('.status-untracked').forEach(el => {
        const title = el.getAttribute('title');
        const status = title.replace('Untracked: ', '');
        statusCounts[status] = (statusCounts[status] || 0) + 1;
    });
    
    console.log('Untracked statuses found:\n');
    Object.entries(statusCounts)
        .sort((a, b) => b[1] - a[1])
        .forEach(([status, count]) => {
            const hasColor = CONFIG.untrackedStatusColors[status];
            const indicator = hasColor ? '🎨' : '⚪';
            console.log(`  ${indicator} ${status}: ${count} segments`);
        });
    
    const unconfigured = Object.keys(statusCounts)
        .filter(status => !CONFIG.untrackedStatusColors[status]);
    
    if (unconfigured.length > 0) {
        console.log('\n⚠️  Statuses without custom colors (will remain grey):');
        unconfigured.forEach(status => {
            console.log(`     - ${status}`);
        });
        console.log('\n   Add these to CONFIG.untrackedStatusColors to colorize them!');
    }
    
    return statusCounts;
}

function resetColors() {
    console.log('🔄 Resetting to default colors...');
    document.querySelectorAll('.status-untracked').forEach(el => {
        el.style.backgroundColor = '';
        el.style.color = '';
        el.style.border = '';
        el.style.fontWeight = '';
        el.textContent = '';
    });
    
    document.querySelectorAll('.timeline-row').forEach(row => {
        row.style.backgroundColor = '';
        row.style.borderLeft = '';
    });
    
    console.log('✓ Colors reset');
}

function previewColors() {
    console.log('\n🎨 Color Preview:\n');
    Object.entries(CONFIG.untrackedStatusColors).forEach(([status, color]) => {
        console.log(`%c ${status} `, 
            `background: ${color}; color: white; padding: 5px 10px; font-weight: bold; margin: 2px;`);
    });
}

function exportConfiguration() {
    console.log('\n📋 Copy this configuration:\n');
    console.log(JSON.stringify(CONFIG.untrackedStatusColors, null, 2));
}

// ============================================================================
// AUTO-RUN
// ============================================================================

// Discover what's in the report
discoverUntrackedStatuses();

// Show color preview
previewColors();

// Apply the colors
applyCustomColors();

// ============================================================================
// AVAILABLE COMMANDS
// ============================================================================

console.log('\n📚 Available commands:');
console.log('  applyCustomColors()       - Reapply colors');
console.log('  resetColors()             - Remove all custom colors');
console.log('  discoverUntrackedStatuses() - List all untracked statuses');
console.log('  previewColors()           - Preview configured colors');
console.log('  exportConfiguration()     - Export color config as JSON');
console.log('\n💡 Tip: Edit the CONFIG section at the top to customize colors!');

// ============================================================================
// BOOKMARKLET VERSION (Copy this entire line to a bookmark)
// ============================================================================
/*
javascript:(function(){const c={'Awaiting Code Review':'%239C27B0','Awaiting Deployment':'%23FF9800','Awaiting QA':'%232196F3','Blocked':'%23F44336','On Hold':'%23FFC107'};Object.entries(c).forEach(([s,col])=>{document.querySelectorAll(`[title^="Untracked: ${s}"]`).forEach(el=>{el.style.backgroundColor=decodeURIComponent(col);el.style.color='white';el.style.fontWeight='bold';if(parseFloat(el.style.width)>5)el.textContent=s;});});console.log('✓ Colors applied');})();
*/
