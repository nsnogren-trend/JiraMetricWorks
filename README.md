# JiraMetricWorks

A desktop application for analyzing Jira data, generating timeline reports, and exporting issue metrics.

## Getting Started

### Prerequisites

- Python 3.8 or higher
- A Jira account with API access

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nsnogren-trend/JiraMetricWorks.git
   cd JiraMetricWorks
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python App/main.py
   ```

### Getting a Jira API Token

1. Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a label (e.g., "JiraMetricWorks") and click **Create**
4. Copy the token — you'll need it to log in

---

## Features & How to Use

### Logging In

1. When the app starts, a **Login** window appears
2. Enter your:
   - **Jira URL**: Your Jira instance URL (e.g., `https://yourcompany.atlassian.net`)
   - **Email**: Your Jira account email
   - **API Token**: The token you generated above
3. Check **Save credentials for future use** if you want to skip login next time
4. Click **Connect**

Once connected, you can switch between Jira instances using **File → Switch Jira Instance** from the menu bar.

---

### Tab 1: Configuration

Use this tab to set up which fields and metrics to include in CSV exports.

#### Step-by-step:

1. **Load Fields from an Issue:**
   - Enter an existing issue key (e.g., `PROJ-123`) in the **Issue Key** field
   - Click **🔄 Load Fields**
   - A list of all fields on that issue appears with example values

2. **Select Fields to Export:**
   - Click the checkbox (✔ column) next to each field you want included in exports

3. **Add Custom Status Transition Rules** (optional):
   - Click **Add Rule** to track time between specific status transitions
   - Enter a **Name** for the rule (e.g., "Development Time")
   - Add the statuses in sequence using the **+** button (e.g., "In Development" → "Code Review")

4. **Configure Other Metrics:**
   - Toggle which built-in metrics to include:
     - Comment Count
     - Comment Length
     - Commenter Count
     - Time in Status

5. **Set Business Hours** (optional):
   - Configure working hours, timezone, and holidays
   - Time-in-status calculations will respect these settings

6. **Save/Load Configuration:**
   - Enter a **Configuration Name** and click **💾 Save Config**
   - Load saved configurations from the dropdown

---

### Tab 2: JQL Search & Export

Use this tab to search for issues and export data.

#### Step-by-step:

1. **Enter a JQL Query:**
   - Type your JQL in the text area (e.g., `project = MYPROJ AND status = Done`)
   - Use the **Saved Queries** dropdown to load previously saved queries
   - Click the **💾** button next to the query field to save the current query

2. **Test Your Query:**
   - Click **🔍 Search** to verify the query and see how many issues match

3. **Export Data:**
   - **📊 Export CSV**: Exports issues with all selected fields and metrics to a CSV file
   - **📄 Export JSON**: Exports each issue as an individual JSON file in a folder
   - **📝 Export Markdown**: Exports each issue as a Markdown file with formatted comments

4. **Monitor Progress:**
   - The progress bar shows export status
   - Logs appear in the console at the bottom of the window

---

### Tab 3: Timeline Report

Generate visual HTML timeline reports showing issue status changes over time.

#### Step-by-step:

1. **Select a Project:**
   - Choose a project from the **Project** dropdown
   - Click **🔄 Refresh** to reload the project list

2. **Define Your Query:**
   - Enter a JQL query to filter which issues appear in the timeline
   - Click **📋 Test Query** to verify it works

3. **Set Date Range** (optional):
   - Enter **Start Date** and **End Date** in `YYYY-MM-DD` format
   - Leave blank to auto-calculate from the data

4. **Configure Status Tracking:**
   - Click **🔄 Load Statuses from Project** to load available statuses
   - For each status you want to track:
     - Enter an **Order** number (lower = earlier in workflow)
     - Optionally set a **Custom Color** using the 🎨 button
   - Only statuses with an order number will appear in the timeline

5. **Generate the Report:**
   - Click **📊 Generate Report**
   - Choose where to save the HTML file
   - The report opens automatically in your browser

6. **Save/Load Configurations:**
   - Click **💾 Save as New Config** to save your current settings
   - Use the **Saved Configuration** dropdown to load previous settings
   - Click **▶️ Run Selected Config** to quickly regenerate a saved report

---

### Tab 4: Sprint Analysis

Analyze status transition patterns within sprints.

#### Step-by-step:

1. **Select a Board:**
   - Choose an Agile board from the **Board** dropdown
   - Click **🔄 Refresh Boards** to reload the list

2. **Select a Sprint:**
   - Once a board is selected, sprints for that board load automatically
   - Choose a sprint from the **Sprint** dropdown
   - Sprint info (dates, status) appears below

3. **Run the Analysis:**
   - Click **🏃 Analyze Sprint Patterns**
   - Results show status transitions with:
     - Issue key
     - From/To status
     - Date of change
     - Sprint day (which day of the sprint)
     - Progress percentage (how far through the sprint)

4. **Export Results:**
   - Click **💾 Export to CSV** to save the analysis data

---

### Managing Saved Connections

To manage multiple Jira instances:

1. Go to **File → Manage Connections**
2. View all saved connections with their URLs and last-used dates
3. **Delete Selected**: Remove a saved connection
4. **Test Connection**: Verify credentials still work

---

## Building a Standalone Executable

To create a standalone `.exe` file:

```bash
# Windows
.\build_executable.bat

# Or using PowerShell
.\build_executable.ps1
```

The executable will be created in the `dist/` folder.

---

## Tips

- **Save frequently used queries** using the 💾 button next to the JQL field
- **Use configurations** to quickly switch between different export setups
- **Timeline reports** are interactive HTML files — hover over bars for details
- **Business hours settings** affect time-in-status calculations for CSV exports
