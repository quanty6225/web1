---
layout: Conceptual
monikers:
- o365-21vianet
- o365-worldwide
defaultMoniker: o365-worldwide
versioningType: Ranged
title: Cancel your Microsoft business subscription in the Microsoft 365 admin center | Microsoft Learn
canonicalUrl: https://learn.microsoft.com/en-us/microsoft-365/commerce/subscriptions/cancel-your-subscription?view=o365-worldwide
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
ms.localizationpriority: high
ms.collection:
- Tier1
- scotvorg
- highpri
- M365-subscription-management
- Adm_O365
ms.custom:
- commerce_subscriptions
- VSBFY23
- AdminSurgePortfolio
- AdminTemplateSet
- admindeeplinkMAC
- GAUpdates
- campaignIDs-batch1
- campaignIDs-batch2
search.appverid: MET150
description: Learn how to cancel your trial or paid subscriptions in the Microsoft 365 admin center.
ms.date: 2026-07-02T00:00:00.0000000Z
locale: en-us
document_id: a91e3ae5-842c-fb3d-8c27-d8001122aee8
document_version_independent_id: ddccec72-7088-4207-60cb-986a35becb67
updated_at: 2026-07-08T18:01:00.0000000Z
original_content_git_url: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/live/microsoft-365/commerce/subscriptions/cancel-your-subscription.md
gitcommit: https://github.com/MicrosoftDocs/microsoft-365-docs-pr/blob/fcfa13351c22c14274da0e2e90274aecad23e044/microsoft-365/commerce/subscriptions/cancel-your-subscription.md
git_commit_id: fcfa13351c22c14274da0e2e90274aecad23e044
default_moniker: o365-worldwide
site_name: Docs
depot_name: office.Microsoft-365-docs
page_type: conceptual
toc_rel: ../toc.json
pdf_url_template: https://learn.microsoft.com/pdfstore/en-us/office.Microsoft-365-docs/{branchName}{pdfName}
feedback_help_link_type: ''
feedback_help_link_url: ''
word_count: 1576
asset_id: commerce/subscriptions/cancel-your-subscription
moniker_range_name: 626dcefb463b053bbc5c86fb8d873ef6
monikers:
- o365-21vianet
- o365-worldwide
item_type: Content
source_path: microsoft-365/commerce/subscriptions/cancel-your-subscription.md
cmProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/1dd701e0-441f-4b0a-9806-aa47decc4e35
- https://microsoft-devrel.poolparty.biz/DevRelOfferingOntology/68e4b2d8-b70c-4019-b49a-d1f8881e2aea
- https://authoring-docs-microsoft.poolparty.biz/devrel/68ec7f3a-2bc6-459f-b959-19beb729907d
spProducts:
- https://authoring-docs-microsoft.poolparty.biz/devrel/0a2fc935-5977-4aa6-9f55-0be03bd2acb8
- https://microsoft-devrel.poolparty.biz/DevRelOfferingOntology/67b2ba1a-6f74-4044-a48a-f0f8ad076b8f
- https://authoring-docs-microsoft.poolparty.biz/devrel/90370425-aca4-4a39-9533-d52e5e002a5d
platformId: d43ec1e2-e29d-13b6-df0d-6e5645be6837
---

# Cancel your Microsoft business subscription in the Microsoft 365 admin center | Microsoft Learn

Check out all of our small business content on [Small business help & learning](https://go.microsoft.com/fwlink/?linkid=2224585).

This article only applies to canceling **Dynamics 365**, **Intune**, **Power Platform**, **Windows 365**, **Microsoft Defender for Business**, and **Microsoft 365 for business** subscriptions. If you have an **Azure** subscription, see [Cancel your Azure subscription](/en-us/azure/cost-management-billing/manage/cancel-azure-subscription). If you have the **Power BI service**, see [Close your account](/en-us/power-bi/enterprise/service-admin-closing-your-account). If you have the **Fabric trial**, see [Cancel your trial](/en-us/power-bi/fundamentals/service-self-service-signup-for-power-bi#trial-expiration).

If you have **Microsoft 365 Family** or **Microsoft 365 Personal**, see [Cancel a Microsoft 365 subscription](https://support.microsoft.com/office/cancel-a-microsoft-365-subscription-46e2634c-c64b-4c65-94b9-2cc9c960e91b?OCID=M365_DocsCancel_Link).

Warning

Before you cancel a subscription, make sure your users save their data.

## Before you begin

- [Find out what type of billing account you have](../manage-billing-accounts#view-my-billing-accounts).
- If you have a Microsoft Customer Agreement (MCA) billing account type, you must be a Billing account owner or contributor, or a Billing profile owner or contributor to do the tasks in this article. For information about Billing account roles and Billing profile roles, see [Understand your Microsoft business billing account](../manage-billing-accounts) and [Manage your Microsoft business billing profiles](../billing-and-payments/manage-billing-profiles).
- If you have a Microsoft Online Subscription Agreement (MOSA), you must be at least a Billing Administrator to do the tasks in this article. For more information, see [About admin roles in the Microsoft 365 admin center](../../admin/add-users/about-admin-roles).
- If you added your own domain name to use with your subscription, you must [remove the domain](../../admin/get-help-with-domains/remove-a-domain) before you cancel your subscription.
- If you have a domain subscription and do not want it to renew, [turn off recurring billing](renew-your-subscription).

Note

If you're the person who signed up for the subscription, you're automatically a Billing account owner.

Important

If you have an MCA billing account type, you automatically receive a product called Microsoft Entra ID Free. Because this product helps manage your billing account, you can't cancel it. If you want to delete your tenant, follow the steps to [Delete a Microsoft Entra Tenant](/en-us/entra/identity/users/directory-delete-howto), or contact Support for help. To learn more, see [Microsoft Entra ID Free](/en-us/azure/cost-management-billing/manage/microsoft-entra-id-free).

## How do I cancel my free trial?

You can cancel your free trial at any time to stop future charges. To cancel a free trial, [turn off recurring billing](renew-your-subscription). If you don't turn off recurring billing, after your one month free trial ends, you're charged the applicable subscription fee. If your trial subscription doesn't have a payment method associated with it, you can just let it expire at the end of the trial period, and you won't be charged.

## What if I bought my subscription through a partner?

If you have an MCA billing account type and bought your subscription through a Microsoft representative or a reseller partner, you have seven days to cancel and receive a pro-rated refund. Contact your seller or partner to help you cancel your subscription. [Learn more about partners](../manage-partners#what-can-a-partner-do-for-my-organization-or-school).

If your organization is in Chile, and you bought your subscription through a partner in Chile, you have 10 days to cancel for a prorated refund.

## Determine your cancellation option

Your cancellation option depends on the type of billing account that you have and how you purchased your subscription. [Find out what type of billing account you have](../manage-billing-accounts#view-my-billing-accounts).

### If you have an MCA billing account type

You can only cancel and receive a prorated credit or refund if you cancel within seven days after the start or renewal of your subscription. If you cancel during this limited time window, the prorated amount is either credited or returned within one to two days.

If you need to cancel within seven days after the start or renewal of your subscription, go to Steps to cancel your subscription later in this article.

If more than seven days have passed since your subscription started or renewed, [turn off recurring billing](renew-your-subscription). Turning off recurring billing prevents your subscription from renewing at the end of its term. You keep access to your products and services for the remainder of your subscription.

If you purchased your subscription from a Microsoft partner or directly from Microsoft, your subscription is eligible for this policy. If you purchased your subscription through a proposal presented to you by a Microsoft seller, then your subscription is not eligible. If you need to amend or change your Microsoft-seller led order for any reason (such as transition subscriptions, change subscriptions, or cancel any subscriptions), please contact your seller.

Note

If you have an annual subscription and are paying monthly, you're charged each month for the remainder of your subscription term.

### If you have an MOSA billing account type

If you cancel after you start or renew your subscription, you receive a prorated credit or refund. The amount is either credited towards your next invoice or returned to you in the next billing cycle.

The steps to cancel your trial or paid subscription depend on the number of licenses in your subscription. The following table explains what steps you can take, based on the number of licenses in your subscription.

| If your subscription has | You can |
| --- | --- |
| 25 or fewer licenses | Use the steps later in this article to cancel your trial or paid subscription online in the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339). |
| More than 25 licenses | [Reduce the number of licenses](../licenses/buy-licenses) to 25 or fewer and then use the steps later in this article to cancel. |

If you're unable to cancel your subscription, [contact support](../../admin/get-help-support) for help.

## Steps to cancel your subscription

You can cancel your subscription in the Microsoft 365 admin center. However, the steps to cancel your subscription depend on the type of billing account that you have. [Find out what type of billing account you have](../manage-billing-accounts#view-my-billing-accounts).

Note

If you have multiple subscriptions for the same product or service, like Microsoft 365 Business Premium, canceling one subscription doesn't affect the licenses, products, or services that you bought for the other subscriptions.

### Cancel your subscription when you have an MCA billing account type

1. Go to the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339).
    - If you're using the **Simplified view**, select **Subscriptions**.
    - If you're using the **Dashboard view**, go to the **Billing** &gt; [Your products](https://go.microsoft.com/fwlink/p/?linkid=842054).
2. Select the subscription that you want to cancel.
3. On the subscription details page, in the **Billing settings** section, under **Subscription status**, select **Cancel subscription**.
4. If you're within the grace period during which you can cancel your subscription, select a reason for why you're canceling, provide optional feedback, then select **Cancel subscription**.
5. If you're outside the grace period, you can only [turn off recurring billing](renew-your-subscription). In the **Canceling your subscription** pane, review the information about how canceling works for your subscription, then select **edit the recurring billing settings**.
6. In the **Edit recurring billing** pane, select **Off**, then select **Save**.
7. Repeat steps 1 through 6 to cancel all active subscriptions.

### Cancel your subscription when you have an MOSA billing account type

1. Go to the [Microsoft 365 admin center](https://go.microsoft.com/fwlink/p/?linkid=2024339).
    - If you're using the **Simplified view**, select **Subscriptions**.
    - If you're using the **Dashboard view**, go to the **Billing** &gt; [Your products](https://go.microsoft.com/fwlink/p/?linkid=842054) page.
2. Select the subscription that you want to cancel.
3. On the subscription details page, in the **Subscription and payment settings** section, select **Cancel subscription**.
4. In the **Options for canceling your subscription** pane, select **Cancel now** or **Cancel before the next renewal date**, then select **Next**.
5. Select a reason for why you're canceling, provide optional feedback, then select **Cancel now**.
6. Repeat steps 1 through 4 to cancel all active subscriptions.

Your subscription status now shows as **Disabled**, and has reduced functionality until it's deleted. For information about what to expect when you cancel a paid Microsoft 365 for business subscription, see [What happens to my data and access when my Microsoft 365 for business subscription ends?](what-if-my-subscription-expires)

Warning

If you explicitly delete a subscription, it skips the **Expired** and **Disabled** states and the SharePoint Online data and content, including OneDrive content, is deleted immediately.

## Save your data

When the cancellation becomes effective, your users lose access to their data. Before you cancel the subscription, have users save their OneDrive for Business or SharePoint Online files to another location. Any customer data that you leave behind might be deleted after 30 days, and is deleted no later than 180 days after cancellation.

- To move email, contacts, tasks, and calendar information to another account, see [Export or backup email, contacts, and calendar to an Outlook .pst file](https://support.microsoft.com/office/14252b52-3075-4e9b-be4e-ff9ef1068f91).
- To save a document library or list content (such as contacts) from a SharePoint Online environment (OneDrive for Business or team sites) to file shares or to a local computer, see [Information about manual migration of SharePoint Online content](/en-us/sharepoint/troubleshoot/migration-tool/content-manual-migration).

For more information, see [What happens to my data and access when my Microsoft 365 for business subscription ends?](what-if-my-subscription-expires)