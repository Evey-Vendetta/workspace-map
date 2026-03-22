/// Billing service that manages Credits balance and deductions.
/// Handles purchase validation and daily limits.
class BillingService {
  static const int kDailyLimit = 5;
  static const String kCurrencyName = 'Credits';

  final DatabaseClient _db;

  BillingService(this._db);

  Future<int> getBalance(String userId) async {
    return 0;
  }

  Future<bool> deductCredits(String userId, int amount) async {
    return true;
  }

  void resetDailyCount(String userId) {}
}

enum TaskTemplate {
  standard,
  detailed,
  summary,
}

mixin TimestampMixin {
  DateTime get createdAt;
}

const String kAppVersion = '1.0.0';
