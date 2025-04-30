/* global use, db */
// MongoDB Carrefour Playground

// Select the database to use.
use('carrefour');

// // Run a find command to view total amounts per month per year.
// db.getCollection('receipts').aggregate([
//   // Step 1: Extract year and month from "attributes.dateKey"
//   {
//     $addFields: {
//       year: { $toInt: { $substr: ["$attributes.dateKey", 0, 4] } }, // Extract year
//       month: { $toInt: { $substr: ["$attributes.dateKey", 4, 2] } } // Extract month
//     }
//   },
//   // Step 4: Group by year and month, and calculate the total amount
//   {
//     $group: {
//       _id: { year: "$year", month: "$month" }, // Group by year and month
//       totalPaidAmount: { $sum: "$attributes.totalPaidAmount" }, // Sum up the totalPaidAmount,
//       totalAmountDeferredDiscount: { $sum: "$attributes.totalAmountDeferredDiscount" }, // Sum up the totalAmountDeferredDiscount
//     }
//   },
//   // Step 5: Sort the results by year and month
//   {
//     $sort: { "_id.year": -1, "_id.month": -1 }
//   }
// ]);

// Run a find command to view the payment information for each receipt.
db.getCollection('receipts').aggregate([
  // Unwind the paymentInfo array to create one document per paymentInfo entry
  { $unwind: "$attributes.paymentInfo" },
  // Project only the necessary fields for the table
  { 
    $project: { 
      _id: 1, 
      dateKey: "$attributes.dateKey",
      totalAmoutPaid: "$attributes.totalPaidAmount",
      totalAmoutDeferredDiscount: "$attributes.totalAmountDeferredDiscount",
      paymentType: "$attributes.paymentInfo.type", 
      paymentChoice: "$attributes.paymentInfo.choice", 
      paymentAmount: "$attributes.paymentInfo.amount" 
    } 
  }
  // {
  //   $group: {
  //     _id: { 
  //       dateKey: "$dateKey", 
  //       paymentType: "$paymentType", 
  //       paymentChoice: "$paymentChoice" 
  //     },
  //   }
  // }
  // {
  //   $group: {
  //     _id: "$paymentType",
  //     totalAmount: { $sum: "$paymentAmount" }
  //   }
  // },

  // {
  //   $sort: { totalAmount: -1 }
  // }
]);