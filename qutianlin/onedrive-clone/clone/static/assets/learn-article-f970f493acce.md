---
layout: Conceptual
monikers:
- o365-21vianet
- o365-worldwide
defaultMoniker: o365-worldwide
versioningType: Ranged
title: Manage recurring billing in the Microsoft 365 admin center | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/microsoft-365/commerce/subscriptions/renew-your-subscription?view=o365-worldwide
config_moniker_range: =o365-worldwide || =o365-21vianet
feedback_system: Standard
feedback_product_url: https://admin.microsoft.com/adminportal/home?showfeedback=DocsMacCampaign
breadcrumb_path: /microsoft-365/breadcrumb/toc.json
recommendations: false
uhfHeaderId: MSDocsHeader-M365-IT
f1.keywords:
- NOCSH
author: cmcatee-MSFT
ms.author: cmcatee
manager: scotv
ms.reviewer: patyc, abjork
audience: Admin
ms.topic: how-to
ms.service: microsoft-365-business
ms.subservice: m365-commerce-acquisition
ms.localizationpriority: medium
ms.collection:
- Tier1
- scotvorg
- highpri
- M365-subscription-management
- Adm_O365
- operations-pod
ms.custom:
- commerce_subscriptions
- VSBFY23
- SaRA
- AdminSurgePortfolio
- AdminTemplateSet
- admindeeplinkMAC
- GAUpdates
- campaignIDs-batch1
search.appverid: MET150
description: Learn how to manage your subscription renewal for a Microsoft business subscription by turning recurring billing off or on.
ms.date: 2026-09-03T00:00:00.0000000Z
locale: en-us
document_id: eb130830-48fe-36e2-4abb-f77258fe7a82
document_version_independent_id: 6a7b2f69-9384-8c20-455f-9c3b2bd24a69
updated_at: 2026-09-11T11:38:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/live/microsoft-365/commerce/subscriptions/renew-your-subscription.md
gitcommit: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/be43c442a232fa4978dff360285d933f059879b0/microsoft-365/commerce/subscriptions/renew-your-subscription.md
git_commit_id: be43c442a232fa4978dff360285d933f059879b0
default_moniker: o365-worldwide
site_name: Docs
depot_name: office.Microsoft-365-docs
page_type: conceptual
toc_rel: ../toc.json
pdf_url_template: https://learn.microsoft.com/pdfstore/en-us/office.Microsoft-365-docs/{branchName}{pdfName}
feedback_help_link_type: ''
feedback_help_link_url: ''
word_count: 555
asset_id: commerce/subscriptions/renew-your-subscription
moniker_range_name: 626dcefb463b053bbc5c86fb8d873ef6
monikers:
- o365-21vianet
- o365-worldwide
item_type: Content
source_path: microsoft-365/commerce/subscriptions/renew-your-subscription.md
cmProducts:
- https://microsoft-devrel.poolparty.biz/DevRelOfferingOntology/68e4b2d8-b70c-4019-b49a-d1f8881e2aea
- https://authoring-docs-microsoft.poolparty.biz/devrel/82f69bd7-5cb0-4163-9fd6-9103bb1a8352
- https://authoring-docs-microsoft.poolparty.biz/devrel/1dd701e0-441f-4b0a-9806-aa47decc4e35
spProducts:
- https://microsoft-devrel.poolparty.biz/DevRelOfferingOntology/67b2ba1a-6f74-4044-a48a-f0f8ad076b8f
- https://authoring-docs-microsoft.poolparty.biz/devrel/f003597a-dab2-429a-8639-1d2acd9c0371
- https://authoring-docs-microsoft.poolparty.biz/devrel/0a2fc935-5977-4aa6-9f55-0be03bd2acb8
platformId: e4b57fa9-c80a-5886-df93-a0ba858745d7
---

# Manage recurring billing in the Microsoft 365 admin center | Microsoft Learn

If you pay for your Microsoft business subscription by using a credit or debit card, or a billing profile, recurring billing is turned on by default. When recurring billing is on, we continue to bill your subscription at the end of the subscription term period. If your subscription is active, you can turn recurring billing off or back on again in the Microsoft 365 admin center.

If you have a prepaid subscription for Microsoft 365 Business Standard that you bought from a retail store or Microsoft partner, you can use a new product key to renew your subscription. For more information, see [Enter your product key for Microsoft 365 Business Standard](../enter-your-product-key).

## Before you begin

- [Find out what type of billing account you have](../manage-billing-accounts#view-my-billing-accounts).
- If you have a Microsoft Customer Agreement (MCA) billing account type, you must be a Billing account owner or contributor, or a Billing profile owner or contributor to do the tasks in this article. For information about billing account and billing profile roles, see [Understand your Microsoft business billing account](../manage-billing-accounts) and [Manage your Microsoft business billing profiles](../billing-and-payments/manage-billing-profiles).
- If you have a Microsoft Online Services Agreement (MOSA), you must be at least a Billing Administrator to do the tasks in this article. For more information, see [About admin roles in the Microsoft 365 admin center](../../admin/add-users/about-admin-roles).

Note

If you're the person who signed up for the subscription, you're automatically a Billing account owner.

## What if I have a prepaid subscription?

If you prepaid for your subscription with a product key, your subscription expires at the end of the subscription term. You can turn on recurring billing and provide credit or debit card information so that your subscription is billed every year on the day that you subscribed. You can also choose to pay every month, or to pay for the entire year up front. Your credit or debit card isn't charged until your initial subscription term expires.

## What happens when I turn off recurring billing?

When you turn off recurring billing for a subscription, it isn't canceled. The subscription remains active until it expires. You can view the expiration date on the [Your products](https://go.microsoft.com/fwlink/p/?linkid=842054) page in the admin center. If you want to keep the subscription active, you must pay the bill manually.

To learn how to cancel a subscription immediately, see [Cancel your Microsoft business subscription](cancel-your-subscription).

Important

Turning off recurring billing cancels any existing scheduled changes you have for a subscription.

## Change the recurring billing setting

You can only change the recurring billing setting for an active subscription. If your subscription has already expired, you must reactivate it before you can turn recurring billing on or off. For more information, see [Reactivate your subscription in the Microsoft 365 admin center](reactivate-your-subscription).

1. Go to the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339).
    - If you're using the **Simplified view**, select **Billing**.
    - If you're using the **Dashboard view**, go to the **Billing** &gt; [Your products](https://go.microsoft.com/fwlink/p/?linkid=842054) page.
2. Select the subscription that you want to manage.
3. On the subscription details page, select **Edit recurring billing**.
4. In the **Edit recurring billing** pane, select On or Off, then select **Save**.