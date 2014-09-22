How to setup LDAP with Windows 2008
===================================

Get an evaluation copy of Windows Server 2008 R2 from:
http://www.microsoft.com/en-us/download/details.aspx?id=2227

The website might ask you to install a download tool, that is not needed.
You might have to abort and just try again.

You need unrar to extract the *.part0X.* files.
Even though the first file is an exe, you don't need Windows to extract it.

If you use VirtualBox, you can proceed to just create a new VM and use the extracted VHD disk image directly as the main HDD.

For the VM you should either add a "Host only" network to reach it from your dev box, or a "Bridged" network if your dev box is on another machine.

The following steps are derived from these pages:
http://stef.thewalter.net/2012/08/how-to-create-active-directory-domain.html
http://technet.microsoft.com/en-us/library/cc754486(v=ws.10).aspx
http://www.windowsnetworking.com/articles-tutorials/windows-server-2008/Configuring-Active-Directory-Lightweight-Directory-Service-Part1.html

Setup the basic stuff:

- Setup Language and Keyboard settings
- Set an admin password when asked
- A list of things to setup should show up
- Set the timezone
- You should enable updates and get the latest updates
- Use "Add roles" near the bottom of the list
- Add "Active Directory Lightweight Directory Services" and proceed with the installation
- Start -> "Administrative Tools" -> "Active Directory Lightweight Directory Services Setup Wizard"
- Create "A unique instance" with the wizard
- Use the defaults
- For "Application directory partition" select "create" and use "CN=Partition1,DC=Woodgrove,DC=COM"
- Select the following LDIF file imports when the list comes up:
  - MS-ADLDS-DisplaySpecifiers.ldf
  - MS-InetOrgPerson.ldf
  - MS-User.ldf
  - MS-UserProxy.ldf
  - MS-UserProxyFull.ldf
- Finish the wizard

Now we can setup LDAP details.
These settings are just for testing and shouldn't be used as a base for a production server.

First the "testuser":

- Start -> "Administrative Tools" -> "ADSI Edit"
- Menu "Action" -> "Connect to"
- Under "Connection Point" select the option with "Distinguished Name"
- Enter "CN=Partition1,DC=Woodgrove,DC=COM"
- Under "Computer" select "domain or server"
- Enter "localhost"
- After connecting, doubleclick in the tree until you see "CN=Partition1,DC=Woodgrove,DC=COM"
- Right click and select "New" -> "Object..."
- select "user"
- Type the user name "testuser" as "Value" and finish the wizard
- In the list right click on the added user and "Reset password ..."
- After that right click and choose "Properties"
- Look for "msDS-UserAccountDisabled" and change it to "False" and "Apply" the changes

Now the group setup:

- In the tree select "CN=Roles"
- "New" -> "Object..."
- select "group"
- Type the group name "testgroup" as "Value" and finish the wizard
- In the list right click on the added group and choose "Properties"
- Look for "member" and add the user with the full distinguished name "CN=testuser,CN=Partition1,DC=Woodgrove,DC=COM"
- Now add the user to the existing group "Readers"

To get the current IP of the VM in case you need it, start the "PowerShell" (should be in the quick start area of the task bar) and type "ipconfig".

After 10 days the installation will ask for activation.
Just leave the product key field blank and continue.
