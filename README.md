# Aurora Plant IT Inventory — Windows LAN Edition v4.7

> **Portfolio / demo build.** This is a sanitized showcase version of an internal IT Asset & Employee
> Inventory system originally built for a power plant's IT department. All company names, logos,
> IP ranges, and records in this repository are fictional/demo data. Default admin login is
> `admin` / `12345678` — you'll be forced to change it on first login.

Company: **Aurora Power Solutions Ltd. (demo company)**

This application runs on one Windows 10/11 office PC. Other authorized devices use Microsoft Edge or Google Chrome to open the same central inventory database over whatever local network the server PC is on — the office LAN, a WiFi network, or any other subnet the PC gets an IP address from.

This is the employee-linked login release. It uses port `8090`, so an old dashboard still running on port `8080` cannot hide the current system. The server window must show `VERSION 4.7`.

## Included

- Secure Admin/User login with hashed passwords
- Protected Main Admin account
- Main Admin-controlled Read, Add/Edit and Delete permissions for Administrators
- User accounts limited to assets assigned to their own Employee ID
- Login account creation directly from the employee list
- Automatic full name, designation and username from Employee ID
- Username rule: `Md.`/`Mohammad` first → second name; otherwise → first name
- Login account editing, disabling, password reset and deletion
- Separate employee directory: Name, ID, Designation and Department
- Departments: I&C, EMD, MMD, A&P, EHS, OPD and RPQC
- Assign devices directly from the In stock asset list
- Automatic device assignment date
- Return workflow that moves devices back to In stock
- Assets show the assigned employee and department
- Permanent employee delete after all devices are returned
- Laptop/Desktop specifications: RAM, CPU, SSD and HDD
- Categories: Laptop, Desktop, Monitor, Mouse, Keyboard, Printer and Server
- Device statuses include Damaged and In warranty
- Central SQLite database and audit trail
- Asset add, edit, delete, search, filter and CSV export
- Arrival Date and Distribution Date tracking (Purchase Value removed)
- Aurora logo and full company name
- Dashboard, maintenance view, reports, dark mode and responsive layout
- Safe database backup and Windows Private-network firewall helper
- Automatic shutdown after eight hours

## First-time setup on the Windows server PC

1. Install Python 3.11 or newer from <https://www.python.org/downloads/windows/>.
2. During installation, select **Add Python to PATH**.
3. Extract this folder to a permanent location such as:

   ```text
   D:\Aurora-IT-Inventory
   ```

4. Set the Windows network profile to **Private**.
5. Right-click `Allow_Private_LAN_Access.bat` and select **Run as administrator**. It allows TCP 8090 from any device on the same network as the server PC (LAN or WiFi, any subnet).
6. Close any older Aurora Inventory black server window.
7. Double-click `Start_Aurora_Inventory.bat`.
8. The browser opens at `http://localhost:8090/login`. The first screen is always the login panel.

The server automatically stops after eight hours. It also stops if you close its black window, sign out of Windows, shut down, restart or put the PC to sleep. Locking Windows does not stop it.

## First login

```text
Username: admin
Password: 12345678
```

The application requires you to change this temporary password on first login before the dashboard opens. After signing in, use **Employees** to add device holders and assign, return or delete employee records. Use **Access Management** to create website login accounts from the Employee list.

For a new account, select the Employee ID. The system automatically fills Name and Designation and creates the Username. If a name starts with `Md.` or `Mohammad`, the second name is used; otherwise the first name is used. A duplicate username receives a short unique suffix.

- **User:** can only see assets currently assigned to that Employee ID and each Distribution Date.
- **Administrator:** sees inventory according to the Read, Add/Edit and Delete permissions selected by the Main Admin.
- **Main Admin:** has full access and manages login accounts.

## Employee device workflow

1. Open **Employees** and select **Add employee**.
2. Enter Name, ID, Designation and one of the approved departments.
3. Select **+ Device** beside that employee.
4. Choose a device from the **In stock** asset list. The assignment date is recorded automatically.
5. The Assets page immediately shows the device as **In use**, with the employee name and department.
6. When the employee returns the device, select **Return**. The asset immediately becomes **In stock** and can be assigned again.
7. To delete an employee, first return all assigned devices, then select the red delete button. A linked login account is deleted with the employee.

## Open from another office PC

1. On the server PC, run `Show_Server_IP.bat`.
2. It lists every IPv4 address the server PC currently has — wired LAN, WiFi, or any other adapter, for example `192.168.50.25` or `192.168.0.14`.
3. On the other PC (connected to the same network, wired or WiFi), open the matching address:

   ```text
   http://<server-ip>:8090/login
   ```

Since the server now listens on all network interfaces, it works over the `192.168.50.0/24` office LAN as well as any WiFi network the server PC joins — the IP address will simply be different on each network. Always use the exact IPv4 shown by `Show_Server_IP.bat` for the network you're currently on. For a stable link on the office LAN, ask the MikroTik/network administrator to reserve that IPv4 address.

Client PCs need only a browser. They do not need Python and do not receive a separate database.

## Database and backup

The central database is stored only on the server PC:

```text
data\inventory.db
```

Run `Backup_Database.bat` for a safe dated copy in the `backups` folder. Existing databases from the earlier release are upgraded automatically; Purchase Date data becomes Arrival Date and Warranty End data becomes Distribution Date.

Keep the application on a permanent local drive. Do not put the live database in OneDrive or a shared network folder. Do not port-forward TCP 8090 or expose this HTTP version to the internet.
