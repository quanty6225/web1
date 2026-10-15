---
layout: Conceptual
monikers:
- o365-21vianet
- o365-worldwide
defaultMoniker: o365-worldwide
versioningType: Ranged
title: Add or replace a onmicrosoft.com fallback domain - Microsoft 365 admin | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/microsoft-365/admin/setup/add-or-replace-your-onmicrosoftcom-domain?view=o365-worldwide
config_moniker_range: =o365-worldwide || =o365-21vianet
feedback_system: Standard
feedback_product_url: https://admin.microsoft.com/adminportal/home?showfeedback=DocsMacCampaign
breadcrumb_path: /microsoft-365/breadcrumb/toc.json
recommendations: false
uhfHeaderId: MSDocsHeader-M365-IT
f1.keywords:
- NOCSH
ms.author: frankroj
author: frankroj
manager: dansimp
ms.date: 2026-04-23T00:00:00.0000000Z
audience: Admin
ms.topic: how-to
ms.service: microsoft-365-business
ms.subservice: m365-domains
ms.localizationpriority: medium
ms.collection:
- Tier2
- scotvorg
- highpri
- M365-subscription-management
- Adm_O365_Setup
- Adm_O365
- Adm_TOC
- operations-pod
ms.custom:
- VSBFY23
- TopSMBIssues
- SaRA
- MSStore_Link
- okr_smb
- business_assist
- AdminSurgePortfolio
- AdminTemplateSet
- domains
search.appverid:
- BCS160
- MET150
- MOE150
ms.assetid: 
description: Learn how to add a new onmicrosoft.com domain and set it as your fallback domain in Microsoft 365. Follow step-by-step instructions to get started.
locale: en-us
document_id: 0a66bd91-6de1-5128-0f77-df1573b7f800
document_version_independent_id: 0a66bd91-6de1-5128-0f77-df1573b7f800
updated_at: 2026-08-20T06:14:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/live/microsoft-365/admin/setup/add-or-replace-your-onmicrosoftcom-domain.md
gitcommit: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/6f6288ab317b06fe93946f851f7880d9fb24333f/microsoft-365/admin/setup/add-or-replace-your-onmicrosoftcom-domain.md
git_commit_id: 6f6288ab317b06fe93946f851f7880d9fb24333f
default_moniker: o365-worldwide
site_name: Docs
depot_name: office.Microsoft-365-docs
page_type: conceptual
toc_rel: ../toc.json
pdf_url_template: https://learn.microsoft.com/pdfstore/en-us/office.Microsoft-365-docs/{branchName}{pdfName}
feedback_help_link_type: ''
feedback_help_link_url: ''
word_count: 832
asset_id: admin/setup/add-or-replace-your-onmicrosoftcom-domain
moniker_range_name: 626dcefb463b053bbc5c86fb8d873ef6
monikers:
- o365-21vianet
- o365-worldwide
item_type: Content
source_path: microsoft-365/admin/setup/add-or-replace-your-onmicrosoftcom-domain.md
cmProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/1dd701e0-441f-4b0a-9806-aa47decc4e35
spProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/0a2fc935-5977-4aa6-9f55-0be03bd2acb8
platformId: df1478b6-5255-5063-0063-1c29e04b5c63
---

# Add or replace a onmicrosoft.com fallback domain - Microsoft 365 admin | Microsoft Learn

When you sign up for Microsoft 365, Microsoft provides an *onmicrosoft.com* domain. The *onmicrosoft.com* domain is your **fallback domain**. Microsoft provides the fallback domain in case you don't own a domain or don't want to connect a domain to Microsoft 365. An example of a fallback domain is:

Important

To prevent misuse and help improve deliverability of customer email, we recommend that onmicrosoft.com domains should only be used for testing purposes, not sending regular email.

Starting **October 15, 2025**, we are introducing limits that might restrict your Microsoft 365 environment from sending to more than 100 external recipients per 24 hours, see: [Limiting Onmicrosoft Domain Usage for Sending Emails](https://techcommunity.microsoft.com/blog/exchange/limiting-onmicrosoft-domain-usage-for-sending-emails/4446167).

When you sign up for Microsoft 365, Microsoft provides an *onmicrosoft.com* domain - your **fallback domain** - in case you don't own a domain, or don't want to connect it to Microsoft 365 (for example, tailspintoys.onmicrosoft.com). Your fallback domain is used by default in:

Use your fallback domain by default in:

- Usernames and email addresses.
- Microsoft 365 teams and groups email aliases.
- Automatic domain dependency moves.

The fallback domain serves as a default email routing address for your Microsoft 365 environment. When you set up a user with a mailbox, email routes to the fallback domain. If you use a custom domain, for example, `tailspintoys.com`, and you delete that custom domain from your Microsoft 365 environment, the fallback domain ensures that your user's email is successfully routed.

You can change your fallback domain in the Microsoft 365 admin center. Common reasons customers change their fallback domain include:

- They didn't know the company name to use when they first signed up for Microsoft 365. Now that they know the company name, they want their users to have sign in account names that are appropriate.
- They want to change how their SharePoint URLs look when they create a new site. SharePoint URLs in your Microsoft 365 environment are created based on your fallback domain name. If you didn't use the correct company name when you first signed up, your SharePoint URLs for your sites continue to use that name when you create new SharePoint sites.

While you can add more onmicrosoft.com domains, you can use only one onmicrosoft.com domain as your fallback domain. The steps in this article describe how to:

- Create a new onmicrosoft.com domain.
- Assign it as your fallback domain.

Warning

You're limited to a total of five onmicrosoft.com domains in your Microsoft 365 environment. Once created, onmicrosoft.com domains can't be deleted.

## Before you begin

To add, modify, or remove domains, you must be a **Domain Name Administrator** of a [business or enterprise plan](https://products.office.com/business/office). These changes affect the whole tenant. *Custom admin roles* or *regular users* can't make these changes.

## Add a new onmicrosoft.com domain

To add a new onmicrosoft.com domain, follow these steps:

1. Sign in to the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339).
2. From the left navigation bar, select **... Show all**, and then select **Settings** to expand it.
3. Under **Settings**, select [**Domains**](https://go.microsoft.com/fwlink/p/?linkid=834818).
4. In the **Domains** page, select your onmicrosoft.com default domain.

    [![Screenshot of the Domains page showing the onmicrosoft.com default domain.](../../media/onmicrosoft-domains.png)](../../media/onmicrosoft-domains.png#lightbox)
5. On the domain properties page, in the **About this domain** section, select **Add onmicrosoft domain**.

    [![Screenshot of the About this domain section with the Add onmicrosoft domain link.](../../media/add-onmicrosoft-domain-link.png)](../../media/add-onmicrosoft-domain-link.png#lightbox)
6. In the **Add onmicrosoft domain** page, in the **Domain name** box, type the name for your new onmicrosoft.com domain.

    [![Screenshot of the Add onmicrosoft domain page with the Domain name box.](../../media/add-an-onmicrosoftcom-domain-page.png)](../../media/add-an-onmicrosoftcom-domain-page.png#lightbox)

    Important

    Make sure to verify the spelling and accuracy of the domain name you entered. You're limited to five onmicrosoft.com domains, and currently you can't delete them once you create them.
7. Select **Add domain**. When you add the domain successfully, you see a message stating that it was successfully added.

    [![Screenshot of the confirmation message indicating the domain was added successfully.](../../media/domain-added.png)](../../media/domain-added.png#lightbox)

## Make your new onmicrosoft.com domain your fallback domain

Tip

Before changing your fallback domain to a new onmicrosoft.com domain, consider changing your onmicrosoft.com SharePoint domain. Creating another onmicrosoft.com domain and using it as your fallback domain doesn't rename SharePoint in Microsoft 365. Your existing SharePoint and OneDrive URLs stay the same.

You can change your.onmicrosoft.com SharePoint domain through the PowerShell steps provided in [SharePoint domain rename preview](/en-us/sharepoint/change-your-sharepoint-domain-name).

After you create your new onmicrosoft.com domain, change your fallback domain:

1. Sign in to the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339).
2. From the left navigation bar, select **... Show all**, and then select **Settings** to expand it.
3. Under **Settings**, select [**Domains**](https://go.microsoft.com/fwlink/p/?linkid=834818).
4. In the **Domains** page, select the new onmicrosoft.com domain that you created.

    [![Screenshot of the Domains page showing the newly added onmicrosoft.com domain.](../../media/onmicrosoft-domains-added.png)](../../media/onmicrosoft-domains-added.png#lightbox)
5. On the domain's property page, select **Make fallback domain**.

    [![Screenshot of the domain property page with the Make fallback domain option.](../../media/new-fallback.png)](../../media/new-fallback.png#lightbox)
6. A message displays on the page stating that your fallback domain changed to the new domain.

    [![Screenshot of the confirmation message indicating the fallback domain was successfully changed.](../../media/fallback-success.png)](../../media/fallback-success.png#lightbox)

## Support

Tip

Some configuration tasks might be complex to perform. For technical support, follow these steps:

1. Sign in to the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339).
2. At the bottom right, select **Help & Support**.
3. In the **Support Assistant** pane that opens, enter your question.
4. Review the results. If you still have questions, select **Contact support**.

To learn about your options for contacting support, see [Get support for Microsoft 365 for business](/en-us/microsoft-365/admin/get-help-support).